import time, math, random, requests
from datetime import datetime, timezone
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt

BASE='https://api.upbit.com/v1'
DAYS=730
MAX_EVENTS=500
MAX_CONTROLS=500
random.seed(42)


def get(path,params=None):
    r=requests.get(BASE+path,params=params,timeout=20,headers={'User-Agent':'DaonFutures-Prepump'})
    r.raise_for_status(); time.sleep(0.11); return r.json()


def daily(market,start,end):
    rows=[]; to=end
    while to>start:
        js=get('/candles/days',{'market':market,'count':200,'to':to.strftime('%Y-%m-%dT%H:%M:%SZ')})
        if not js: break
        rows.extend(js); old=pd.Timestamp(js[-1]['candle_date_time_utc'],tz='UTC')
        if old<=start: break
        to=old-pd.Timedelta(seconds=1)
    if not rows: return pd.DataFrame()
    d=pd.DataFrame(rows); d['time']=pd.to_datetime(d['candle_date_time_utc'],utc=True)
    d=d.drop_duplicates('time').set_index('time').sort_index()
    out=pd.DataFrame(index=d.index)
    out['open']=pd.to_numeric(d.opening_price); out['high']=pd.to_numeric(d.high_price); out['close']=pd.to_numeric(d.trade_price); out['value']=pd.to_numeric(d.candle_acc_trade_price)
    out['sma50']=out.close.rolling(50).mean(); out['age']=np.arange(1,len(out)+1)
    return out.loc[(out.index>=start)&(out.index<=end)]


def mins15(market,signal_t):
    # 6 hours ending exactly at the signal timestamp; only pre-signal candles are used.
    js=get('/candles/minutes/15',{'market':market,'count':24,'to':signal_t.strftime('%Y-%m-%dT%H:%M:%SZ')})
    if not js: return pd.DataFrame()
    d=pd.DataFrame(js); d['time']=pd.to_datetime(d['candle_date_time_utc'],utc=True)
    d=d[d.time<signal_t].sort_values('time')
    if len(d)<20: return pd.DataFrame()
    out=pd.DataFrame(index=d.time)
    out['open']=pd.to_numeric(d.opening_price).values; out['high']=pd.to_numeric(d.high_price).values; out['low']=pd.to_numeric(d.low_price).values; out['close']=pd.to_numeric(d.trade_price).values; out['value']=pd.to_numeric(d.candle_acc_trade_price).values
    return out


def features(x):
    if len(x)<20: return None
    c=x.close.values; v=x.value.values
    eps=1e-12
    last15=v[-1]; prev12=v[-13:-1]
    val15=last15/(np.mean(prev12)+eps)
    val1h=np.sum(v[-4:]); prev4h=np.sum(v[-20:-4])/4.0
    val1h_ratio=val1h/(prev4h+eps)
    accel=(np.sum(v[-2:])+eps)/(np.sum(v[-4:-2])+eps)
    ret15=c[-1]/c[-2]-1; ret1h=c[-1]/c[-5]-1; ret4h=c[-1]/c[-17]-1
    rng1h=(np.max(x.high.values[-4:])-np.min(x.low.values[-4:]))/(c[-5]+eps)
    vol=np.std(np.diff(np.log(c[-13:])))
    prior_high=np.max(x.high.values[-17:-1])
    breakout_dist=c[-1]/(prior_high+eps)-1
    return {'value15_ratio':val15,'value1h_ratio':val1h_ratio,'value_accel':accel,'ret15':ret15,'ret1h':ret1h,'ret4h':ret4h,'range1h':rng1h,'vol15':vol,'breakout_dist':breakout_dist}


def main():
    end=pd.Timestamp(datetime.now(timezone.utc)).floor('D'); start=end-pd.Timedelta(days=DAYS+80)
    markets=[x['market'] for x in get('/market/all',{'is_details':'false'}) if x['market'].startswith('KRW-')]
    all_daily={}; candidates=[]; controls=[]
    for n,m in enumerate(markets,1):
        try:
            d=daily(m,start,end)
            if len(d)<180: continue
            all_daily[m]=d
            idx=list(d.index)
            for i in range(60,len(idx)-1):
                t=idx[i]; nxt=idx[i+1]
                r=d.loc[t]
                if r.age<120 or not np.isfinite(r.value) or r.value<500_000_000: continue
                # Signal is known at t open (= prior daily close). Outcome is maximum move during next 24h candle.
                base=float(d.loc[t,'open']); fut_high=float(d.loc[t,'high'])
                if base<=0: continue
                move=fut_high/base-1
                rec=(m,t,move,float(r.value))
                if move>=0.20: candidates.append(rec)
                elif move<0.08: controls.append(rec)
        except Exception as e: print('daily skip',m,e,flush=True)
        if n%25==0 or n==len(markets): print('daily',n,'/',len(markets),flush=True)
    print('raw events',len(candidates),'controls',len(controls),flush=True)
    candidates=sorted(candidates,key=lambda z:z[2],reverse=True)[:MAX_EVENTS]
    random.shuffle(controls); controls=controls[:MAX_CONTROLS]
    samples=[]
    for label,arr in [(1,candidates),(0,controls)]:
        for j,(m,t,move,dval) in enumerate(arr,1):
            try:
                x=mins15(m,t); f=features(x)
                if f is None: continue
                row={'market':m,'signal_time':t,'label':label,'future24h_high_pct':move*100,'daily_value_krw':dval}
                row.update(f); samples.append(row)
            except Exception as e: print('15m skip',m,t,e,flush=True)
            if j%100==0: print('15m label',label,j,'/',len(arr),flush=True)
    s=pd.DataFrame(samples).sort_values('signal_time').reset_index(drop=True)
    if len(s)<100: raise RuntimeError('not enough samples')
    split=int(len(s)*0.70); tr=s.iloc[:split].copy(); te=s.iloc[split:].copy()
    feats=['value15_ratio','value1h_ratio','value_accel','ret15','ret1h','ret4h','range1h','vol15','breakout_dist']
    # Direction and strength are learned only on training data using standardized event-vs-control mean differences.
    weights={}; stats={}
    for f in feats:
        mu=tr[f].mean(); sd=tr[f].std() or 1.0
        e=tr.loc[tr.label==1,f].mean(); c=tr.loc[tr.label==0,f].mean(); w=(e-c)/(sd+1e-12)
        weights[f]=float(np.clip(w,-3,3)); stats[f]=(float(mu),float(sd))
    def score(df):
        z=np.zeros(len(df))
        for f in feats:
            mu,sd=stats[f]; z+=weights[f]*((df[f].values-mu)/(sd+1e-12))
        return z
    tr['score']=score(tr); te['score']=score(te)
    base=float(te.label.mean())
    rows=[]
    for frac in [0.50,0.25,0.10,0.05]:
        q=te.score.quantile(1-frac); sub=te[te.score>=q]
        hit=float(sub.label.mean()) if len(sub) else np.nan
        rows.append({'segment':f'TOP_{int(frac*100)}PCT_SCORE','samples':len(sub),'event_hit_rate_pct':hit*100,'baseline_event_rate_pct':base*100,'lift_x':hit/base if base>0 else np.nan,'avg_future24h_high_pct':float(sub.future24h_high_pct.mean()),'median_future24h_high_pct':float(sub.future24h_high_pct.median())})
    # Threshold-specific event prevalence in top score decile.
    q=te.score.quantile(0.90); top=te[te.score>=q]
    for th in [20,30,50]:
        rate=float((top.future24h_high_pct>=th).mean()) if len(top) else np.nan
        allrate=float((te.future24h_high_pct>=th).mean())
        rows.append({'segment':f'TOP10_FUTURE_GE_{th}','samples':len(top),'event_hit_rate_pct':rate*100,'baseline_event_rate_pct':allrate*100,'lift_x':rate/allrate if allrate>0 else np.nan,'avg_future24h_high_pct':float(top.future24h_high_pct.mean()),'median_future24h_high_pct':float(top.future24h_high_pct.median())})
    res=pd.DataFrame(rows)
    res.to_csv('backtest_results.csv',index=False)
    s.to_csv('prepump_samples.csv',index=False)
    pd.DataFrame([{'feature':f,'weight':weights[f]} for f in feats]).sort_values('weight',ascending=False).to_csv('prepump_feature_weights.csv',index=False)
    plt.figure(figsize=(10,6))
    plot=res[res.segment.str.startswith('TOP_')].copy()
    plt.bar(plot.segment,plot.lift_x); plt.axhline(1.0,linestyle='--'); plt.ylabel('Lift vs baseline'); plt.title('Upbit Pre-pump Money-flow Signal - Out-of-sample Lift'); plt.xticks(rotation=25,ha='right'); plt.tight_layout(); plt.savefig('backtest_equity.png',dpi=150)
    print('\nRESULTS\n',res.to_string(index=False),flush=True)
    print('\nFEATURE WEIGHTS\n',pd.DataFrame([{'feature':f,'weight':weights[f]} for f in feats]).sort_values('weight',ascending=False).to_string(index=False),flush=True)
    print('\nSAMPLES',len(s),'TRAIN',len(tr),'TEST',len(te),flush=True)
    print('STRICT TIMING: all features use only 15m candles ending BEFORE signal timestamp; outcome is subsequent 24h high.',flush=True)
    print('NOTE: current-listed-market survivorship bias remains; this is discovery, not a tradable strategy yet.',flush=True)

if __name__=='__main__': main()
