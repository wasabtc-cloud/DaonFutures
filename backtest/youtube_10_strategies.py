import time, random, threading, requests
from collections import deque
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt

BASE='https://api.upbit.com/v1'; DAYS=730; MAX_EVENTS=180; MAX_CONTROLS=360; SEED=42
random.seed(SEED)
RATE_LOCK=threading.Lock(); CALLS=deque(); MAX_RPS=8
# Frozen from the prior OOS optimization. Do not retune these on the test set.
BLUE_Q=.94; GREEN_WINDOW=20; GREEN_VALUE5=1.0; GREEN_ACCEL5=1.1
FEE=.0005; SLIP=.0003

def throttle():
    while True:
        with RATE_LOCK:
            now=time.monotonic()
            while CALLS and now-CALLS[0]>=1.0: CALLS.popleft()
            if len(CALLS)<MAX_RPS:
                CALLS.append(now); return
            wait=max(.01,1.0-(now-CALLS[0])+.005)
        time.sleep(wait)

def get(path,params=None,retries=5):
    for k in range(retries):
        throttle()
        try:
            r=requests.get(BASE+path,params=params,timeout=25,headers={'User-Agent':'DaonFutures-EntryStop'})
            if r.status_code==429:
                time.sleep(.5*(k+1)); continue
            r.raise_for_status(); return r.json()
        except Exception:
            if k==retries-1: raise
            time.sleep(.35*(k+1))

def daily(m,s,e):
    rows=[]; to=e
    while to>s:
        js=get('/candles/days',{'market':m,'count':200,'to':to.strftime('%Y-%m-%dT%H:%M:%SZ')})
        if not js: break
        rows+=js; old=pd.Timestamp(js[-1]['candle_date_time_utc'],tz='UTC')
        if old<=s: break
        to=old-pd.Timedelta(seconds=1)
    if not rows:return pd.DataFrame()
    d=pd.DataFrame(rows); d['time']=pd.to_datetime(d.candle_date_time_utc,utc=True); d=d.drop_duplicates('time').set_index('time').sort_index()
    o=pd.DataFrame(index=d.index); o['open']=pd.to_numeric(d.opening_price);o['high']=pd.to_numeric(d.high_price);o['value']=pd.to_numeric(d.candle_acc_trade_price);o['value20']=o.value.rolling(20).mean()
    return o.loc[(o.index>=s)&(o.index<=e)]

def minute(m,t):
    rows=[]; end=t+pd.Timedelta(days=1,hours=6); to=end
    for _ in range(12):
        js=get('/candles/minutes/1',{'market':m,'count':200,'to':to.strftime('%Y-%m-%dT%H:%M:%SZ')})
        if not js:break
        rows+=js; old=pd.Timestamp(js[-1]['candle_date_time_utc'],tz='UTC')
        if old<=t-pd.Timedelta(minutes=90):break
        to=old-pd.Timedelta(seconds=1)
    if not rows:return pd.DataFrame()
    d=pd.DataFrame(rows);d['time']=pd.to_datetime(d.candle_date_time_utc,utc=True);d=d.drop_duplicates('time').set_index('time').sort_index();d=d.loc[(d.index>=t-pd.Timedelta(minutes=90))&(d.index<end)]
    o=pd.DataFrame(index=d.index)
    for a,b in [('open','opening_price'),('high','high_price'),('low','low_price'),('close','trade_price'),('value','candle_acc_trade_price')]:o[a]=pd.to_numeric(d[b])
    return o

def features(x,t):
    if len(x)<120:return pd.DataFrame()
    e=1e-12;c=x.close;v=x.value;h=x.high;l=x.low;f=pd.DataFrame(index=x.index)
    f['open']=x.open;f['high']=h;f['low']=l;f['close']=c
    f['value1_ratio']=v/(v.shift(1).rolling(20).mean()+e);f['value5_ratio']=v.rolling(5).sum()/(v.shift(5).rolling(55).sum()/11+e);f['value_accel5']=v.rolling(5).sum()/(v.shift(5).rolling(5).sum()+e)
    for n in [1,5,15,60]:f[f'ret{n}']=c.pct_change(n)
    hi=h.shift(1).rolling(60).max();lo=l.shift(1).rolling(60).min();f['range60']=(hi-lo)/(c.shift(60)+e);f['breakout60']=c/(hi+e)-1;f['vol15']=np.log(c).diff().rolling(15).std();f['price']=c
    pc=c.shift(1);tr=np.maximum(h-l,np.maximum((h-pc).abs(),(l-pc).abs()));f['atr14']=tr.rolling(14).mean()
    for n in [5,10,20]:f[f'swing{n}']=l.shift(1).rolling(n).min()
    return f.loc[f.index>=t+pd.Timedelta(minutes=60)].replace([np.inf,-np.inf],np.nan).dropna()

def load_day(item):
    lab,m,t,mv=item
    try:
        f=features(minute(m,t),t)
        if len(f)>100:
            f['market']=m;f['day_start']=t;f['day_label']=lab
            return f
    except Exception as z: print('1m skip',m,t,z,flush=True)
    return None

def main():
    end=pd.Timestamp(datetime.now(timezone.utc)).floor('D');start=end-pd.Timedelta(days=DAYS+100)
    markets=[x['market'] for x in get('/market/all',{'is_details':'false'}) if x['market'].startswith('KRW-')]
    ev=[];co=[]
    for n,m in enumerate(markets,1):
        try:
            d=daily(m,start,end)
            for i in range(120,max(120,len(d)-1)):
                if not np.isfinite(d.value20.iloc[i]) or d.value20.iloc[i]<5e8:continue
                move=d.high.iloc[i]/d.open.iloc[i]-1;rec=(m,d.index[i],move)
                if move>=.20:ev.append(rec)
                elif move<.08:co.append(rec)
        except Exception as z:print('daily skip',m,z,flush=True)
        if n%25==0 or n==len(markets):print('daily',n,'/',len(markets),flush=True)
    ev=sorted(ev,key=lambda z:z[1])
    if len(ev)>MAX_EVENTS:ev=[ev[i] for i in np.linspace(0,len(ev)-1,MAX_EVENTS).astype(int)]
    random.shuffle(co);co=co[:MAX_CONTROLS]
    sel=sorted([(1,*r) for r in ev]+[(0,*r) for r in co],key=lambda z:z[2])
    frames=[];done=0
    print('parallel 1m fetch',len(sel),'days',flush=True)
    with ThreadPoolExecutor(max_workers=8) as ex:
        futs=[ex.submit(load_day,item) for item in sel]
        for fut in as_completed(futs):
            done+=1;f=fut.result()
            if f is not None:frames.append(f)
            if done%25==0 or done==len(sel):print('1m days',done,'/',len(sel),flush=True)
    meta=sorted([(f.day_start.iloc[0],i) for i,f in enumerate(frames)]);cut=meta[int(len(meta)*.70)][0]
    train=pd.concat([f for f in frames if f.day_start.iloc[0]<=cut]);tests=[f for f in frames if f.day_start.iloc[0]>cut]
    cols=['value1_ratio','value5_ratio','value_accel5','ret1','ret5','ret15','ret60','range60','vol15','breakout60'];ts=train.iloc[::10].copy();ts['y']=(ts.high.shift(-1).rolling(360,min_periods=1).max().shift(-359)/ts.close-1>=.20).astype(int)
    stats={};w={}
    for c in cols:
        mu=float(ts[c].mean());sd=float(ts[c].std()) or 1;p=float(ts.loc[ts.y==1,c].mean());q=float(ts.loc[ts.y==0,c].mean());stats[c]=(mu,sd);w[c]=float(np.clip((p-q)/(sd+1e-12),-3,3))
    def score(d):
        z=np.zeros(len(d))
        for c in cols:mu,sd=stats[c];z+=w[c]*((d[c].values-mu)/(sd+1e-12))
        return z
    ts['score']=score(ts);th=float(ts.score.quantile(BLUE_Q))

    stop_defs=[]
    for n in [5,10,20]: stop_defs.append((f'SWING{n}',('swing',n,0)))
    for mult in [1.0,1.5,2.0,2.5]: stop_defs.append((f'ATR{mult:.1f}',('atr',0,mult)))
    trade_rows=[]
    for d0 in tests:
        d=d0.copy();d['score']=score(d);b=d[d.score>=th]
        if b.empty: continue
        bt=b.index[0];win=d.loc[bt:bt+pd.Timedelta(minutes=GREEN_WINDOW)]
        g=win[(win.value5_ratio>=GREEN_VALUE5)&(win.value_accel5>=GREEN_ACCEL5)&(win.ret5>0)&(win.ret15>0)]
        if g.empty: continue
        gt=g.index[0]
        pos=d.index.get_indexer([gt])[0]
        if pos<0 or pos+1>=len(d): continue
        entry_time=d.index[pos+1]; entry_raw=float(d.open.iloc[pos+1]); entry=entry_raw*(1+SLIP)
        horizon=d.loc[entry_time:entry_time+pd.Timedelta(hours=6)]
        if len(horizon)<2: continue
        label=int(d.day_label.iloc[0]); market=d.market.iloc[0]
        for name,sd in stop_defs:
            typ,n,mult=sd
            if typ=='swing': raw=float(d.loc[gt,f'swing{n}'])
            else: raw=float(d.loc[gt,'close']-mult*d.loc[gt,'atr14'])
            stop=raw*(1-SLIP)
            if not np.isfinite(stop) or stop<=0 or stop>=entry: continue
            risk=(entry-stop)/entry
            if risk<.002 or risk>.20: continue
            highs=horizon.high.values;lows=horizon.low.values
            stop_hit=False;hit2=False;hit3=False;exit_r=np.nan
            for hi,lo in zip(highs,lows):
                # Conservative same-bar ordering: stop is checked before profit targets.
                if lo<=stop:
                    stop_hit=True;exit_r=-1.0;break
                if hi>=entry+3*(entry-stop): hit3=True
                if hi>=entry+2*(entry-stop): hit2=True
            mfe=float(np.max(highs)/entry-1); mae=float(np.min(lows)/entry-1)
            net_stop_r=(-risk-FEE*2)/risk if risk>0 else np.nan
            trade_rows.append({'market':market,'label':label,'green_time':gt,'entry_time':entry_time,'stop_type':name,'entry':entry,'stop':stop,'risk_pct':risk*100,'stop_hit':int(stop_hit),'hit_2r':int(hit2),'hit_3r':int(hit3),'mfe_pct':mfe*100,'mae_pct':mae*100,'net_stop_r':net_stop_r})
    tr=pd.DataFrame(trade_rows)
    if tr.empty: raise RuntimeError('No trade rows produced')
    sums=[]
    for name,gp in tr.groupby('stop_type'):
        sums.append({'stop_type':name,'trades':len(gp),'event_share_pct':gp.label.mean()*100,'avg_risk_pct':gp.risk_pct.mean(),'median_risk_pct':gp.risk_pct.median(),'stop_hit_pct':gp.stop_hit.mean()*100,'hit_2r_pct':gp.hit_2r.mean()*100,'hit_3r_pct':gp.hit_3r.mean()*100,'avg_mfe_pct':gp.mfe_pct.mean(),'median_mfe_pct':gp.mfe_pct.median(),'avg_mae_pct':gp.mae_pct.mean()})
    s=pd.DataFrame(sums)
    # Prefer high 2R conversion and lower stop rate, penalize excessively wide stops.
    s['score']=s.hit_2r_pct-0.45*s.stop_hit_pct-0.8*np.maximum(0,s.avg_risk_pct-8)
    s=s.sort_values('score',ascending=False).reset_index(drop=True)
    best=s.iloc[0]
    out=pd.DataFrame([
        ('TEST_GREEN_SIGNALS',int(tr.green_time.nunique())),('BEST_STOP_TYPE',best.stop_type),('BEST_TRADES',best.trades),('BEST_AVG_RISK_PCT',best.avg_risk_pct),('BEST_STOP_HIT_PCT',best.stop_hit_pct),('BEST_HIT_2R_PCT',best.hit_2r_pct),('BEST_HIT_3R_PCT',best.hit_3r_pct),('BEST_AVG_MFE_PCT',best.avg_mfe_pct),('BEST_MEDIAN_MFE_PCT',best.median_mfe_pct),('BEST_AVG_MAE_PCT',best.avg_mae_pct),('ENTRY_SLIPPAGE_PCT',SLIP*100),('FEE_PER_SIDE_PCT',FEE*100),('BLUE_Q',BLUE_Q),('GREEN_WINDOW_MIN',GREEN_WINDOW),('GREEN_VALUE5_GATE',GREEN_VALUE5),('GREEN_ACCEL5_GATE',GREEN_ACCEL5)
    ],columns=['metric','value'])
    out.to_csv('backtest_results.csv',index=False);s.to_csv('entry_stop_grid.csv',index=False);tr.to_csv('entry_stop_trades.csv',index=False)
    plt.figure(figsize=(10,6));x=np.arange(len(s));plt.bar(x,s.hit_2r_pct,label='2R hit %');plt.plot(x,s.stop_hit_pct,marker='o',label='Stop hit %');plt.xticks(x,s.stop_type,rotation=30);plt.ylabel('%');plt.title('DaonFutures OOS Entry + Stop Comparison');plt.legend();plt.tight_layout();plt.savefig('backtest_equity.png',dpi=150)
    print('\nENTRY + STOP OOS SUMMARY\n',out.to_string(index=False),flush=True)
    print('\nSTOP GRID\n',s.to_string(index=False),flush=True)
    print('ENTRY RULE: GREEN is confirmed on a completed 1m candle; entry is NEXT 1m candle open plus 0.03% slippage.',flush=True)
    print('STRICT CAUSAL: all stop inputs are known at GREEN time; future 6h is evaluation only.',flush=True)
    print('CONSERVATIVE: if stop and target are touched in the same 1m bar, stop is counted first.',flush=True)
    print('NOTE: case-control sampling remains; this chooses a stop candidate, not yet a natural-prevalence portfolio PnL.',flush=True)
if __name__=='__main__':main()
