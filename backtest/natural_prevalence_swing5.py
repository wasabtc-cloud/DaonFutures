import time, random, threading, requests
from collections import deque
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
import numpy as np
import pandas as pd

BASE='https://api.upbit.com/v1'
SEED=42; random.seed(SEED)
TRAIN_DAYS=730; VALID_DAYS=365; TOP_MARKETS=20
MAX_EVENTS=180; MAX_CONTROLS=360
BLUE_Q=.94; GREEN_WINDOW=20; GREEN_VALUE5=1.0; GREEN_ACCEL5=1.1
FEE=.0005; SLIP=.0003; MAX_RPS=8; HORIZON_MINUTES=360; TRAIL_LOOKBACK=20
RATE_LOCK=threading.Lock(); CALLS=deque()

def throttle():
    while True:
        with RATE_LOCK:
            now=time.monotonic()
            while CALLS and now-CALLS[0]>=1.0: CALLS.popleft()
            if len(CALLS)<MAX_RPS:
                CALLS.append(now); return
            wait=max(.01,1.0-(now-CALLS[0])+.005)
        time.sleep(wait)

def get(path,params=None,retries=6):
    for k in range(retries):
        throttle()
        try:
            r=requests.get(BASE+path,params=params,timeout=30,headers={'User-Agent':'DaonFutures-Natural-SWING5'})
            if r.status_code==429:
                time.sleep(.6*(k+1)); continue
            r.raise_for_status(); return r.json()
        except Exception:
            if k==retries-1: raise
            time.sleep(.5*(k+1))

def daily(m,s,e):
    rows=[]; to=e
    while to>s:
        js=get('/candles/days',{'market':m,'count':200,'to':to.strftime('%Y-%m-%dT%H:%M:%SZ')})
        if not js: break
        rows+=js; old=pd.Timestamp(js[-1]['candle_date_time_utc'],tz='UTC')
        if old<=s: break
        to=old-pd.Timedelta(seconds=1)
    if not rows:return pd.DataFrame()
    d=pd.DataFrame(rows);d['time']=pd.to_datetime(d.candle_date_time_utc,utc=True);d=d.drop_duplicates('time').set_index('time').sort_index()
    o=pd.DataFrame(index=d.index);o['open']=pd.to_numeric(d.opening_price);o['high']=pd.to_numeric(d.high_price);o['value']=pd.to_numeric(d.candle_acc_trade_price);o['value20']=o.value.rolling(20).mean()
    return o.loc[(o.index>=s)&(o.index<=e)]

def minute_window(m,t):
    rows=[];end=t+pd.Timedelta(days=1,hours=6);to=end
    for _ in range(12):
        js=get('/candles/minutes/1',{'market':m,'count':200,'to':to.strftime('%Y-%m-%dT%H:%M:%SZ')})
        if not js:break
        rows+=js;old=pd.Timestamp(js[-1]['candle_date_time_utc'],tz='UTC')
        if old<=t-pd.Timedelta(minutes=90):break
        to=old-pd.Timedelta(seconds=1)
    return normalize_minutes(rows,t-pd.Timedelta(minutes=90),end)

def fetch_continuous_minutes(m,start,end):
    rows=[];to=end+pd.Timedelta(minutes=1);n=0
    while to>start:
        js=get('/candles/minutes/1',{'market':m,'count':200,'to':to.strftime('%Y-%m-%dT%H:%M:%SZ')})
        if not js:break
        rows+=js;n+=1;old=pd.Timestamp(js[-1]['candle_date_time_utc'],tz='UTC')
        if old<=start:break
        to=old-pd.Timedelta(seconds=1)
        if n%500==0: print(f'{m} minute pages {n}',flush=True)
    return normalize_minutes(rows,start,end)

def normalize_minutes(rows,start,end):
    if not rows:return pd.DataFrame()
    d=pd.DataFrame(rows);d['time']=pd.to_datetime(d.candle_date_time_utc,utc=True);d=d.drop_duplicates('time').set_index('time').sort_index();d=d.loc[(d.index>=start)&(d.index<=end)]
    o=pd.DataFrame(index=d.index)
    for a,b in [('open','opening_price'),('high','high_price'),('low','low_price'),('close','trade_price'),('value','candle_acc_trade_price')]:o[a]=pd.to_numeric(d[b])
    return o

def features(x,start=None):
    if len(x)<120:return pd.DataFrame()
    e=1e-12;c=x.close;v=x.value;h=x.high;l=x.low;f=pd.DataFrame(index=x.index)
    f['open']=x.open;f['high']=h;f['low']=l;f['close']=c
    f['value1_ratio']=v/(v.shift(1).rolling(20).mean()+e);f['value5_ratio']=v.rolling(5).sum()/(v.shift(5).rolling(55).sum()/11+e);f['value_accel5']=v.rolling(5).sum()/(v.shift(5).rolling(5).sum()+e)
    for n in [1,5,15,60]:f[f'ret{n}']=c.pct_change(n)
    hi=h.shift(1).rolling(60).max();lo=l.shift(1).rolling(60).min();f['range60']=(hi-lo)/(c.shift(60)+e);f['breakout60']=c/(hi+e)-1;f['vol15']=np.log(c).diff().rolling(15).std();f['price']=c
    pc=c.shift(1);tr=np.maximum(h-l,np.maximum((h-pc).abs(),(l-pc).abs()));f['atr14']=tr.rolling(14).mean();f['swing5']=l.shift(1).rolling(5).min()
    f=f.replace([np.inf,-np.inf],np.nan).dropna()
    if start is not None:f=f.loc[f.index>=start]
    return f

def load_train_day(item):
    lab,m,t,mv=item
    try:
        f=features(minute_window(m,t),t+pd.Timedelta(minutes=60))
        if len(f)>100:
            f['market']=m;f['day_start']=t;f['day_label']=lab;return f
    except Exception as z:print('train skip',m,t,z,flush=True)
    return None

def train_model(markets,end):
    start=end-pd.Timedelta(days=TRAIN_DAYS+100);ev=[];co=[]
    for n,m in enumerate(markets,1):
        try:
            d=daily(m,start,end)
            for i in range(120,max(120,len(d)-1)):
                if not np.isfinite(d.value20.iloc[i]) or d.value20.iloc[i]<5e8:continue
                move=d.high.iloc[i]/d.open.iloc[i]-1;rec=(m,d.index[i],move)
                if move>=.20:ev.append(rec)
                elif move<.08:co.append(rec)
        except Exception as z:print('daily skip',m,z,flush=True)
        if n%25==0 or n==len(markets):print('training daily',n,'/',len(markets),flush=True)
    ev=sorted(ev,key=lambda z:z[1])
    if len(ev)>MAX_EVENTS:ev=[ev[i] for i in np.linspace(0,len(ev)-1,MAX_EVENTS).astype(int)]
    random.shuffle(co);co=co[:MAX_CONTROLS]
    sel=sorted([(1,*r) for r in ev]+[(0,*r) for r in co],key=lambda z:z[2])
    frames=[];done=0
    with ThreadPoolExecutor(max_workers=8) as ex:
        futs=[ex.submit(load_train_day,item) for item in sel]
        for fut in as_completed(futs):
            done+=1;f=fut.result()
            if f is not None:frames.append(f)
            if done%50==0 or done==len(sel):print('training 1m',done,'/',len(sel),flush=True)
    meta=sorted([(f.day_start.iloc[0],i) for i,f in enumerate(frames)]);cut=meta[int(len(meta)*.70)][0]
    train=pd.concat([f for f in frames if f.day_start.iloc[0]<=cut])
    cols=['value1_ratio','value5_ratio','value_accel5','ret1','ret5','ret15','ret60','range60','vol15','breakout60'];ts=train.iloc[::10].copy();ts['y']=(ts.high.shift(-1).rolling(360,min_periods=1).max().shift(-359)/ts.close-1>=.20).astype(int)
    stats={};w={}
    for c in cols:
        mu=float(ts[c].mean());sd=float(ts[c].std()) or 1;p=float(ts.loc[ts.y==1,c].mean());q=float(ts.loc[ts.y==0,c].mean());stats[c]=(mu,sd);w[c]=float(np.clip((p-q)/(sd+1e-12),-3,3))
    z=np.zeros(len(ts))
    for c in cols:mu,sd=stats[c];z+=w[c]*((ts[c].values-mu)/(sd+1e-12))
    th=float(pd.Series(z).quantile(BLUE_Q))
    print('TRAIN CUT',cut,'THRESHOLD',th,flush=True)
    return cols,stats,w,th,cut

def score_frame(d,cols,stats,w):
    z=np.zeros(len(d))
    for c in cols:mu,sd=stats[c];z+=w[c]*((d[c].values-mu)/(sd+1e-12))
    return z

def simulate(path,entry,initial_stop):
    risk=entry-initial_stop
    if risk<=0 or path.empty:return np.nan,'invalid'
    tp2=entry+2*risk;tp3=entry+3*risk;active=initial_stop;partial=False;realized=0.;remaining=1.;lows=[]
    for _,bar in path.iterrows():
        lo=float(bar.low);hi=float(bar.high);lows.append(lo)
        if lo<=active:
            fill=active*(1-SLIP);rr=(fill-entry)/risk-(entry*FEE+fill*FEE)/risk
            return realized+remaining*rr,'stop_or_trail'
        if not partial and hi>=tp2:
            fill=tp2*(1-SLIP);rr=(fill-entry)/risk-(entry*FEE+fill*FEE)/risk
            realized+=.5*rr;remaining=.5;partial=True;active=max(active,entry);continue
        if partial:
            if len(lows)>=TRAIL_LOOKBACK+1:active=max(active,min(lows[-(TRAIL_LOOKBACK+1):-1]))
            if hi>=tp3:
                fill=tp3*(1-SLIP);rr=(fill-entry)/risk-(entry*FEE+fill*FEE)/risk
                return realized+remaining*rr,'runner_3R'
    fill=float(path.close.iloc[-1])*(1-SLIP);rr=(fill-entry)/risk-(entry*FEE+fill*FEE)/risk
    return realized+remaining*rr,'time_exit'

def market_universe(markets,anchor):
    s=anchor-pd.Timedelta(days=60);rows=[]
    for n,m in enumerate(markets,1):
        try:
            d=daily(m,s,anchor)
            past=d.loc[d.index<anchor].tail(30)
            if len(past)>=20:rows.append((m,float(past.value.mean())))
        except Exception:pass
        if n%50==0:print('universe',n,'/',len(markets),flush=True)
    rows=sorted(rows,key=lambda x:x[1],reverse=True)[:TOP_MARKETS]
    print('VALIDATION UNIVERSE',rows,flush=True)
    return [x[0] for x in rows]

def max_dd(rvals):
    eq=100.;peak=eq;mdd=0.
    for r in rvals:
        eq*=max(0.,1.+.01*float(r));peak=max(peak,eq);mdd=max(mdd,(peak-eq)/peak)
    return mdd*100,eq

def loss_streak(rvals):
    best=cur=0
    for r in rvals:
        if r<0:cur+=1;best=max(best,cur)
        else:cur=0
    return best

def main():
    end=pd.Timestamp(datetime.now(timezone.utc)).floor('D');markets=[x['market'] for x in get('/market/all',{'is_details':'false'}) if x['market'].startswith('KRW-')]
    cols,stats,w,th,train_cut=train_model(markets,end)
    valid_start=max(train_cut+pd.Timedelta(days=1),end-pd.Timedelta(days=VALID_DAYS))
    universe=market_universe(markets,valid_start)
    trades=[]
    for ix,m in enumerate(universe,1):
        print(f'VALIDATE {ix}/{len(universe)} {m}',flush=True)
        raw=fetch_continuous_minutes(m,valid_start-pd.Timedelta(minutes=120),end)
        d=features(raw,valid_start)
        if d.empty:continue
        d['score']=score_frame(d,cols,stats,w)
        i=0;idx=d.index
        while i<len(d)-2:
            if d.score.iloc[i]<th:i+=1;continue
            bt=idx[i];j=i;limit=bt+pd.Timedelta(minutes=GREEN_WINDOW);green=None
            while j<len(d) and idx[j]<=limit:
                row=d.iloc[j]
                if row.value5_ratio>=GREEN_VALUE5 and row.value_accel5>=GREEN_ACCEL5 and row.ret5>0 and row.ret15>0:
                    green=j;break
                j+=1
            if green is None:i=j+1;continue
            if green+1>=len(d):break
            entry_time=idx[green+1];entry=float(d.open.iloc[green+1])*(1+SLIP);stop=float(d.swing5.iloc[green])*(1-SLIP)
            risk_pct=(entry-stop)/entry*100
            if not np.isfinite(stop) or stop<=0 or stop>=entry or risk_pct<.2 or risk_pct>20:
                i=green+1;continue
            path=raw.loc[(raw.index>=entry_time)&(raw.index<=entry_time+pd.Timedelta(minutes=HORIZON_MINUTES))]
            rr,reason=simulate(path,entry,stop)
            if np.isfinite(rr):trades.append({'market':m,'blue_time':bt,'green_time':idx[green],'entry_time':entry_time,'entry':entry,'stop':stop,'risk_pct':risk_pct,'result_r':rr,'exit_reason':reason})
            cooldown=entry_time+pd.Timedelta(minutes=HORIZON_MINUTES)
            i=int(idx.searchsorted(cooldown,side='left'))
    tr=pd.DataFrame(trades)
    if tr.empty:raise RuntimeError('No natural-prevalence trades produced')
    tr=tr.sort_values('entry_time').reset_index(drop=True);r=tr.result_r.astype(float);gp=r[r>0].sum();gl=-r[r<0].sum();pf=gp/gl if gl>0 else np.inf;mdd,ending=max_dd(r.values)
    summary=pd.DataFrame([{'validation_start':valid_start,'validation_end':end,'markets':len(universe),'trades':len(tr),'win_rate_pct':(r>0).mean()*100,'avg_r':r.mean(),'median_r':r.median(),'profit_factor_r':pf,'avg_risk_pct':tr.risk_pct.mean(),'mdd_pct_at_1pct_risk':mdd,'ending_equity_at_1pct_risk':ending,'max_consecutive_losses':loss_streak(r.values),'positive_2r_plus_pct':(r>=2).mean()*100}])
    tr['month']=pd.to_datetime(tr.entry_time,utc=True).dt.to_period('M').astype(str)
    monthly=tr.groupby('month').agg(trades=('result_r','size'),avg_r=('result_r','mean'),sum_r=('result_r','sum'),win_rate_pct=('result_r',lambda x:(x>0).mean()*100)).reset_index()
    tr.to_csv('natural_swing5_trades.csv',index=False);summary.to_csv('natural_swing5_summary.csv',index=False);monthly.to_csv('natural_swing5_monthly.csv',index=False)
    print('\nNATURAL PREVALENCE SWING5 SUMMARY\n',summary.to_string(index=False),flush=True)
    print('\nMONTHLY\n',monthly.to_string(index=False),flush=True)
    print('\nNOTE: validation universe is top 20 KRW markets ranked by trailing 30-day value known at validation start; no future move label is used in validation.',flush=True)
    print('EXIT: 2R 50% partial, breakeven, prior-20 completed 1m low trail, 3R cap, 6h horizon, fees/slippage included.',flush=True)
    print('PORTFOLIO METRICS: chronological 1% equity risk per trade; simultaneous multi-market exposure is not capped in this first natural-prevalence pass.',flush=True)

if __name__=='__main__':main()
