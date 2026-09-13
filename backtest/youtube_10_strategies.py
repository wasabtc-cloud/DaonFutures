import time, random, requests
from datetime import datetime, timezone
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt

BASE='https://api.upbit.com/v1'
DAYS=730
MAX_EVENTS=180
MAX_CONTROLS=360
SEED=42
random.seed(SEED)


def get(path, params=None):
    r=requests.get(BASE+path, params=params, timeout=25, headers={'User-Agent':'DaonFutures-1mEarlyFlow'})
    r.raise_for_status(); time.sleep(0.115); return r.json()


def daily(market,start,end):
    rows=[]; to=end
    while to>start:
        js=get('/candles/days',{'market':market,'count':200,'to':to.strftime('%Y-%m-%dT%H:%M:%SZ')})
        if not js: break
        rows.extend(js)
        old=pd.Timestamp(js[-1]['candle_date_time_utc'],tz='UTC')
        if old<=start: break
        to=old-pd.Timedelta(seconds=1)
    if not rows: return pd.DataFrame()
    d=pd.DataFrame(rows); d['time']=pd.to_datetime(d['candle_date_time_utc'],utc=True)
    d=d.drop_duplicates('time').set_index('time').sort_index()
    out=pd.DataFrame(index=d.index)
    out['open']=pd.to_numeric(d.opening_price)
    out['high']=pd.to_numeric(d.high_price)
    out['close']=pd.to_numeric(d.trade_price)
    out['value']=pd.to_numeric(d.candle_acc_trade_price)
    out['value20']=out.value.rolling(20).mean()
    out['age']=np.arange(1,len(out)+1)
    return out.loc[(out.index>=start)&(out.index<=end)]


def minute1_day(market, day_start):
    # Fetch a complete 24h window in backward pages. Each page uses only historical candles.
    day_end=day_start+pd.Timedelta(days=1)
    rows=[]; to=day_end
    for _ in range(9):
        js=get('/candles/minutes/1',{'market':market,'count':200,'to':to.strftime('%Y-%m-%dT%H:%M:%SZ')})
        if not js: break
        rows.extend(js)
        old=pd.Timestamp(js[-1]['candle_date_time_utc'],tz='UTC')
        if old<=day_start-pd.Timedelta(minutes=70): break
        to=old-pd.Timedelta(seconds=1)
    if not rows: return pd.DataFrame()
    d=pd.DataFrame(rows); d['time']=pd.to_datetime(d['candle_date_time_utc'],utc=True)
    d=d.drop_duplicates('time').set_index('time').sort_index()
    d=d.loc[(d.index>=day_start-pd.Timedelta(minutes=70))&(d.index<day_end)]
    out=pd.DataFrame(index=d.index)
    out['open']=pd.to_numeric(d.opening_price)
    out['high']=pd.to_numeric(d.high_price)
    out['low']=pd.to_numeric(d.low_price)
    out['close']=pd.to_numeric(d.trade_price)
    out['value']=pd.to_numeric(d.candle_acc_trade_price)
    return out


def build_features(x, day_start):
    if len(x)<120: return pd.DataFrame()
    eps=1e-12
    c=x.close; v=x.value; h=x.high; l=x.low
    f=pd.DataFrame(index=x.index)
    # All features at minute t use current/previous completed 1m candles only.
    f['value1_ratio']=v/(v.shift(1).rolling(20).mean()+eps)
    f['value5_ratio']=v.rolling(5).sum()/(v.shift(5).rolling(55).sum()/11.0+eps)
    f['value_accel5']=v.rolling(5).sum()/(v.shift(5).rolling(5).sum()+eps)
    f['ret1']=c.pct_change(1)
    f['ret5']=c.pct_change(5)
    f['ret15']=c.pct_change(15)
    f['ret60']=c.pct_change(60)
    prior_hi=h.shift(1).rolling(60).max(); prior_lo=l.shift(1).rolling(60).min()
    f['range60']=(prior_hi-prior_lo)/(c.shift(60)+eps)
    f['breakout60']=c/(prior_hi+eps)-1
    f['vol15']=np.log(c).diff().rolling(15).std()
    f['price']=c
    # Future outcomes are labels only, never inputs: max high over NEXT 6h and NEXT 24h from each minute.
    hv=h.values; cv=c.values; n=len(x)
    fut6=np.full(n,np.nan); fut24=np.full(n,np.nan)
    for i in range(n):
        if cv[i]<=0: continue
        j6=min(n,i+361); j24=n
        if i+1<j6: fut6[i]=np.max(hv[i+1:j6])/cv[i]-1
        if i+1<j24: fut24[i]=np.max(hv[i+1:j24])/cv[i]-1
    f['future6h']=fut6; f['future24h']=fut24
    f=f.loc[f.index>=day_start+pd.Timedelta(minutes=60)].replace([np.inf,-np.inf],np.nan).dropna()
    return f


def main():
    end=pd.Timestamp(datetime.now(timezone.utc)).floor('D')
    start=end-pd.Timedelta(days=DAYS+100)
    markets=[x['market'] for x in get('/market/all',{'is_details':'false'}) if x['market'].startswith('KRW-')]
    events=[]; controls=[]
    for n,m in enumerate(markets,1):
        try:
            d=daily(m,start,end)
            if len(d)<180: continue
            for i in range(120,len(d)-1):
                t=d.index[i]
                if not np.isfinite(d.value20.iloc[i]) or d.value20.iloc[i]<500_000_000: continue
                base=float(d.open.iloc[i]); hi=float(d.high.iloc[i])
                if base<=0: continue
                move=hi/base-1
                rec=(m,t,move)
                if move>=0.20: events.append(rec)
                elif move<0.08: controls.append(rec)
        except Exception as e: print('daily skip',m,e,flush=True)
        if n%25==0 or n==len(markets): print('daily',n,'/',len(markets),flush=True)
    print('raw events',len(events),'controls',len(controls),flush=True)
    # Spread event samples across time rather than choosing only the biggest pumps.
    events=sorted(events,key=lambda z:z[1])
    if len(events)>MAX_EVENTS:
        ix=np.linspace(0,len(events)-1,MAX_EVENTS).astype(int); events=[events[i] for i in ix]
    random.shuffle(controls); controls=controls[:MAX_CONTROLS]
    selected=[(1,*r) for r in events]+[(0,*r) for r in controls]
    selected=sorted(selected,key=lambda z:z[2])

    day_frames=[]
    day_meta=[]
    for j,(day_label,m,t,dmove) in enumerate(selected,1):
        try:
            x=minute1_day(m,t); f=build_features(x,t)
            if len(f)<100: continue
            f['market']=m; f['day_start']=t; f['day_label']=day_label; f['daily_move']=dmove
            day_frames.append(f)
            day_meta.append((m,t,day_label,dmove))
        except Exception as e: print('1m skip',m,t,e,flush=True)
        if j%25==0 or j==len(selected): print('1m days',j,'/',len(selected),flush=True)
    if len(day_frames)<100: raise RuntimeError('not enough 1m day samples')

    # Chronological split by day. Learn feature directions and threshold on first 70%, test untouched last 30%.
    meta=pd.DataFrame(day_meta,columns=['market','day_start','day_label','daily_move']).sort_values('day_start')
    cut=meta.day_start.quantile(0.70)
    train=pd.concat([f for f in day_frames if f.day_start.iloc[0]<=cut]).sort_index()
    test_days=[f for f in day_frames if f.day_start.iloc[0]>cut]
    feats=['value1_ratio','value5_ratio','value_accel5','ret1','ret5','ret15','ret60','range60','vol15','breakout60']

    # Sample every 10th train minute to reduce serial dependence. Positive minute = +20% reachable in next 6h.
    ts=train.iloc[::10].copy(); ts['y']=(ts.future6h>=0.20).astype(int)
    stats={}; weights={}
    for col in feats:
        mu=float(ts[col].mean()); sd=float(ts[col].std()) or 1.0
        p=float(ts.loc[ts.y==1,col].mean()) if (ts.y==1).any() else mu
        q=float(ts.loc[ts.y==0,col].mean()) if (ts.y==0).any() else mu
        weights[col]=float(np.clip((p-q)/(sd+1e-12),-3,3)); stats[col]=(mu,sd)
    def score(df):
        z=np.zeros(len(df))
        for col in feats:
            mu,sd=stats[col]; z+=weights[col]*((df[col].values-mu)/(sd+1e-12))
        return z
    ts['score']=score(ts)
    # Threshold chosen ONLY on train: search high quantiles, maximize precision with at least 40 sampled minute signals.
    best=None
    for q in [0.90,0.92,0.94,0.95,0.96,0.97,0.98,0.99]:
        th=float(ts.score.quantile(q)); sub=ts[ts.score>=th]
        if len(sub)<40: continue
        prec=float(sub.y.mean()); metric=prec*(1+0.15*q)
        if best is None or metric>best[0]: best=(metric,q,th,prec,len(sub))
    if best is None: raise RuntimeError('threshold search failed')
    _,train_q,threshold,train_precision,train_n=best

    rows=[]; signal_rows=[]
    for f in test_days:
        d=f.copy(); d['score']=score(d)
        sig=d[d.score>=threshold]
        if len(sig)==0:
            rows.append({'market':d.market.iloc[0],'day_start':d.day_start.iloc[0],'day_label':int(d.day_label.iloc[0]),'signal':0,'signal_time':pd.NaT,'signal_price':np.nan,'future6h_pct':np.nan,'future24h_pct':np.nan,'score':np.nan})
            continue
        s=sig.iloc[0]
        rec={'market':s.market,'day_start':s.day_start,'day_label':int(s.day_label),'signal':1,'signal_time':s.name,'signal_price':float(s.price),'future6h_pct':float(s.future6h*100),'future24h_pct':float(s.future24h*100),'score':float(s.score)}
        rows.append(rec); signal_rows.append(rec)
    r=pd.DataFrame(rows).sort_values('day_start')
    sig=r[r.signal==1].copy()
    def pct(mask): return float(mask.mean()*100) if len(mask) else np.nan
    summary=[]
    summary.append({'metric':'TEST_DAYS','value':len(r)})
    summary.append({'metric':'SIGNAL_DAYS','value':len(sig)})
    summary.append({'metric':'SIGNAL_RATE_PCT','value':pct(r.signal==1)})
    summary.append({'metric':'TRAIN_THRESHOLD_QUANTILE','value':train_q})
    summary.append({'metric':'TRAIN_MINUTE_PRECISION_PCT','value':train_precision*100})
    summary.append({'metric':'SIGNAL_FUTURE6H_GE20_PCT','value':pct(sig.future6h_pct>=20)})
    summary.append({'metric':'SIGNAL_FUTURE6H_GE30_PCT','value':pct(sig.future6h_pct>=30)})
    summary.append({'metric':'SIGNAL_FUTURE6H_GE50_PCT','value':pct(sig.future6h_pct>=50)})
    summary.append({'metric':'SIGNAL_FUTURE24H_GE20_PCT','value':pct(sig.future24h_pct>=20)})
    summary.append({'metric':'AVG_FUTURE6H_PCT','value':float(sig.future6h_pct.mean()) if len(sig) else np.nan})
    summary.append({'metric':'MEDIAN_FUTURE6H_PCT','value':float(sig.future6h_pct.median()) if len(sig) else np.nan})
    # Day-level recall on known +20% event days vs false alert rate on controls.
    ev=r[r.day_label==1]; co=r[r.day_label==0]
    summary.append({'metric':'EVENT_DAY_SIGNAL_RECALL_PCT','value':pct(ev.signal==1)})
    summary.append({'metric':'CONTROL_DAY_FALSE_SIGNAL_PCT','value':pct(co.signal==1)})
    summary.append({'metric':'SIGNAL_EVENT_DAY_SHARE_PCT','value':pct(sig.day_label==1)})

    out=pd.DataFrame(summary)
    out.to_csv('backtest_results.csv',index=False)
    r.to_csv('one_minute_signal_days.csv',index=False)
    pd.DataFrame([{'feature':k,'weight':v} for k,v in weights.items()]).sort_values('weight',ascending=False).to_csv('one_minute_feature_weights.csv',index=False)

    plt.figure(figsize=(10,6))
    names=['6h>=20','6h>=30','6h>=50','24h>=20']
    vals=[pct(sig.future6h_pct>=20),pct(sig.future6h_pct>=30),pct(sig.future6h_pct>=50),pct(sig.future24h_pct>=20)]
    plt.bar(names,vals); plt.ylim(0,100); plt.ylabel('Hit rate %'); plt.title('DaonFutures 1m Early Money-flow Signal - OOS'); plt.tight_layout(); plt.savefig('backtest_equity.png',dpi=150)

    print('\n1M EARLY FLOW RESULTS\n',out.to_string(index=False),flush=True)
    print('\nFEATURE WEIGHTS\n',pd.DataFrame([{'feature':k,'weight':v} for k,v in weights.items()]).sort_values('weight',ascending=False).to_string(index=False),flush=True)
    print('\nDAYS',len(r),'SIGNALS',len(sig),'TRAIN_Q',train_q,'THRESHOLD',threshold,flush=True)
    print('STRICT CAUSALITY: each alert uses only completed 1m candles at/before that minute. Future 6h/24h highs are labels only.',flush=True)
    print('NOTE: sampled event/control days and current-listed-market survivorship bias remain. This is validation, not a profit guarantee.',flush=True)

if __name__=='__main__': main()
