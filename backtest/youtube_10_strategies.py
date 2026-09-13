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

def throttle():
    while True:
        with RATE_LOCK:
            now=time.monotonic()
            while CALLS and now-CALLS[0]>=1.0: CALLS.popleft()
            if len(CALLS)<MAX_RPS:
                CALLS.append(now); return
            wait=max(0.01,1.0-(now-CALLS[0])+0.005)
        time.sleep(wait)

def get(path,params=None,retries=5):
    for k in range(retries):
        throttle()
        try:
            r=requests.get(BASE+path,params=params,timeout=25,headers={'User-Agent':'DaonFutures-GreenOptimize'})
            if r.status_code==429:
                time.sleep(0.5*(k+1)); continue
            r.raise_for_status(); return r.json()
        except Exception:
            if k==retries-1: raise
            time.sleep(0.35*(k+1))

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
    rows=[]; end=t+pd.Timedelta(days=1); to=end
    for _ in range(8):
        js=get('/candles/minutes/1',{'market':m,'count':200,'to':to.strftime('%Y-%m-%dT%H:%M:%SZ')})
        if not js:break
        rows+=js; old=pd.Timestamp(js[-1]['candle_date_time_utc'],tz='UTC')
        if old<=t-pd.Timedelta(minutes=70):break
        to=old-pd.Timedelta(seconds=1)
    if not rows:return pd.DataFrame()
    d=pd.DataFrame(rows);d['time']=pd.to_datetime(d.candle_date_time_utc,utc=True);d=d.drop_duplicates('time').set_index('time').sort_index();d=d.loc[(d.index>=t-pd.Timedelta(minutes=70))&(d.index<end)]
    o=pd.DataFrame(index=d.index)
    for a,b in [('open','opening_price'),('high','high_price'),('low','low_price'),('close','trade_price'),('value','candle_acc_trade_price')]:o[a]=pd.to_numeric(d[b])
    return o

def features(x,t):
    if len(x)<120:return pd.DataFrame()
    e=1e-12;c=x.close;v=x.value;h=x.high;l=x.low;f=pd.DataFrame(index=x.index)
    f['value1_ratio']=v/(v.shift(1).rolling(20).mean()+e);f['value5_ratio']=v.rolling(5).sum()/(v.shift(5).rolling(55).sum()/11+e);f['value_accel5']=v.rolling(5).sum()/(v.shift(5).rolling(5).sum()+e)
    for n in [1,5,15,60]:f[f'ret{n}']=c.pct_change(n)
    hi=h.shift(1).rolling(60).max();lo=l.shift(1).rolling(60).min();f['range60']=(hi-lo)/(c.shift(60)+e);f['breakout60']=c/(hi+e)-1;f['vol15']=np.log(c).diff().rolling(15).std();f['price']=c
    hv=h.values;cv=c.values;n=len(x);f6=np.full(n,np.nan)
    for i in range(n):
        j=min(n,i+361)
        if i+1<j and cv[i]>0:f6[i]=np.max(hv[i+1:j])/cv[i]-1
    f['future6h']=f6
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
    cols=['value1_ratio','value5_ratio','value_accel5','ret1','ret5','ret15','ret60','range60','vol15','breakout60'];ts=train.iloc[::10].copy();ts['y']=(ts.future6h>=.20).astype(int);stats={};w={}
    for c in cols:
        mu=float(ts[c].mean());sd=float(ts[c].std()) or 1;p=float(ts.loc[ts.y==1,c].mean());q=float(ts.loc[ts.y==0,c].mean());stats[c]=(mu,sd);w[c]=float(np.clip((p-q)/(sd+1e-12),-3,3))
    def score(d):
        z=np.zeros(len(d))
        for c in cols:mu,sd=stats[c];z+=w[c]*((d[c].values-mu)/(sd+1e-12))
        return z
    ts['score']=score(ts)
    train_days=[f for f in frames if f.day_start.iloc[0]<=cut]
    grid=[]
    for q in [0.88,0.90,0.92,0.94]:
      th=float(ts.score.quantile(q))
      for winmin in [5,10,15,20]:
       for vr in [1.0,1.15,1.3,1.5,1.75]:
        for acc in [1.0,1.1,1.2,1.35,1.5]:
         tp=fp=evn=con=greens=0
         for d0 in train_days:
            lab=int(d0.day_label.iloc[0]);evn+=lab;con+=1-lab;d=d0.copy();d['score']=score(d);b=d[d.score>=th]
            if b.empty:continue
            win=d.loc[b.index[0]:b.index[0]+pd.Timedelta(minutes=winmin)]
            g=win[(win.value5_ratio>=vr)&(win.value_accel5>=acc)&(win.ret5>0)&(win.ret15>0)]
            if not g.empty:
                greens+=1;tp+=lab;fp+=1-lab
         recall=tp/evn if evn else 0;false=fp/con if con else 1
         objective=recall-1.8*max(0,false-.10)-0.3*false
         grid.append((objective,recall,false,greens,q,th,winmin,vr,acc))
    grid.sort(reverse=True,key=lambda x:x[0])
    pd.DataFrame(grid,columns=['objective','train_recall','train_false','green_days','blue_quantile','threshold','window_min','value5_gate','accel5_gate']).to_csv('green_grid_results.csv',index=False)
    candidates=[x for x in grid if x[1]>=.80 and x[2]<=.12]
    best=(candidates[0] if candidates else grid[0]);_,trrec,trfalse,trn,q,th,winmin,vr,acc=best
    rows=[]
    for d0 in tests:
        d=d0.copy();d['score']=score(d);b=d[d.score>=th];rec={'label':int(d.day_label.iloc[0]),'blue':0,'green':0,'future6h':np.nan,'entry_ret15':np.nan}
        if not b.empty:
            rec['blue']=1;bt=b.index[0];win=d.loc[bt:bt+pd.Timedelta(minutes=winmin)];g=win[(win.value5_ratio>=vr)&(win.value_accel5>=acc)&(win.ret5>0)&(win.ret15>0)]
            if not g.empty:
                s=g.iloc[0];rec['green']=1;rec['future6h']=float(s.future6h*100);rec['entry_ret15']=float(s.ret15*100)
        rows.append(rec)
    r=pd.DataFrame(rows);g=r[r.green==1];evr=r[r.label==1];cor=r[r.label==0]
    pct=lambda x:float(x.mean()*100) if len(x) else np.nan
    out=pd.DataFrame([('TEST_DAYS',len(r)),('BLUE_DAYS',r.blue.sum()),('GREEN_DAYS',r.green.sum()),('GREEN_RATE_PCT',pct(r.green==1)),('TRAIN_EVENT_RECALL_PCT',trrec*100),('TRAIN_CONTROL_FALSE_PCT',trfalse*100),('GREEN_FUTURE6H_GE20_PCT',pct(g.future6h>=20)),('GREEN_FUTURE6H_GE30_PCT',pct(g.future6h>=30)),('GREEN_FUTURE6H_GE50_PCT',pct(g.future6h>=50)),('GREEN_AVG_FUTURE6H_PCT',g.future6h.mean()),('EVENT_GREEN_RECALL_PCT',pct(evr.green==1)),('CONTROL_GREEN_FALSE_PCT',pct(cor.green==1)),('GREEN_EVENT_SHARE_PCT',pct(g.label==1)),('BLUE_THRESHOLD_QUANTILE',q),('GREEN_WINDOW_MIN',winmin),('GREEN_VALUE5_GATE',vr),('GREEN_ACCEL5_GATE',acc)],columns=['metric','value'])
    out.to_csv('backtest_results.csv',index=False);r.to_csv('green_signal_days.csv',index=False);pd.DataFrame([{'feature':k,'weight':v} for k,v in w.items()]).to_csv('one_minute_feature_weights.csv',index=False)
    plt.figure(figsize=(9,6));plt.bar(['BLUE','GREEN','GREEN +20%'],[r.blue.mean()*100,r.green.mean()*100,pct(g.future6h>=20)]);plt.ylim(0,100);plt.ylabel('%');plt.title('DaonFutures Optimized Blue to Green OOS');plt.tight_layout();plt.savefig('backtest_equity.png',dpi=150)
    print('\nOPTIMIZED BLUE->GREEN RESULTS\n',out.to_string(index=False),flush=True)
    print('BEST',{'q':q,'window':winmin,'value5':vr,'accel5':acc},flush=True)
    print('STRICT CAUSAL: GREEN uses only completed candles at signal time. Future6h is label only.',flush=True)
    print('NOTE: case-control sampling remains; this is confirmation validation, not natural-prevalence PnL.',flush=True)
if __name__=='__main__':main()
