"""Research-only, Wonyotti-inspired pattern/candle/volume backtest.

This is NOT a reproduction of Wonyotti's proprietary method. It operationalizes only
publicly reported principles: candle+volume pattern recognition, trading familiar setups,
cutting when the pattern invalidates, letting winners run, and strict risk management.
No live orders are placed.
"""
from __future__ import annotations
import time, math, requests
import numpy as np
import pandas as pd
from datetime import datetime, timezone

BASE='https://api.binance.com/api/v3'
SYMBOL='BTCUSDT'
INTERVAL='15m'
DAYS=365
LOOKBACK=32
FORWARD=16              # 4 hours on 15m bars
HIST_WINDOW=96*45        # 45 days of prior 15m patterns
K=12
MIN_SIM=0.88
MIN_CONSENSUS=0.67
FEE_SLIP_PCT=0.12        # round-trip research drag
RISK_PER_TRADE=0.01


def get_klines(start_ms,end_ms):
    rows=[]; cur=start_ms
    while cur<end_ms:
        r=requests.get(BASE+'/klines',params={'symbol':SYMBOL,'interval':INTERVAL,'startTime':cur,'endTime':end_ms,'limit':1000},timeout=30)
        r.raise_for_status(); js=r.json()
        if not js:break
        rows.extend(js)
        cur=int(js[-1][0])+1
        time.sleep(.05)
        if len(js)<1000:break
    d=pd.DataFrame(rows,columns=['open_time','open','high','low','close','volume','close_time','qv','trades','tbv','tbqv','ignore'])
    for c in ['open','high','low','close','volume','qv']:d[c]=pd.to_numeric(d[c])
    d['time']=pd.to_datetime(d.open_time,unit='ms',utc=True)
    return d.drop_duplicates('time').set_index('time').sort_index()


def vec(window:pd.DataFrame):
    c=window.close.values.astype(float)
    v=window.qv.values.astype(float)
    r=np.diff(np.log(c),prepend=np.log(c[0]))
    vn=np.log1p(v/(np.median(v)+1e-12))
    z=np.r_[r, vn]
    z=(z-z.mean())/(z.std()+1e-12)
    return z


def cosine(a,b):
    return float(np.dot(a,b)/((np.linalg.norm(a)*np.linalg.norm(b))+1e-12))


def choose_signal(df,i):
    if i<LOOKBACK+HIST_WINDOW or i+FORWARD>=len(df):return None
    now=vec(df.iloc[i-LOOKBACK:i])
    start=max(LOOKBACK,i-HIST_WINDOW)
    candidates=[]
    # sample every 4 bars to reduce dependence + speed
    for j in range(start,i-FORWARD-4,4):
        x=vec(df.iloc[j-LOOKBACK:j])
        s=cosine(now,x)
        if s<MIN_SIM:continue
        fut=float(df.close.iloc[j+FORWARD]/df.close.iloc[j]-1)
        candidates.append((s,fut,j))
    if len(candidates)<K:return None
    top=sorted(candidates,reverse=True)[:K]
    fw=np.array([x[1] for x in top]); sims=np.array([x[0] for x in top])
    direction=1 if np.median(fw)>0 else -1
    consensus=float((np.sign(fw)==direction).mean())
    if consensus<MIN_CONSENSUS:return None
    # volume must not be dead vs its recent baseline
    q=df.qv.iloc[i-8:i].sum(); qb=df.qv.iloc[i-96:i-8].rolling(8).sum().median()
    vr=float(q/(qb+1e-12)) if np.isfinite(qb) else 0
    if vr<0.8:return None
    return {'direction':direction,'consensus':consensus,'similarity':float(sims.mean()),'median_future':float(np.median(fw)),'value_ratio':vr}


def run_trade(df,i,sig):
    entry=float(df.open.iloc[i+1]); direction=sig['direction']
    # structural stop: prior 8-bar swing (2h); cap risk at 2.5%
    if direction>0:
        structural=float(df.low.iloc[i-8:i].min()); stop=max(structural,entry*(1-0.025)); risk=(entry-stop)/entry
    else:
        structural=float(df.high.iloc[i-8:i].max()); stop=min(structural,entry*(1+0.025)); risk=(stop-entry)/entry
    if risk<0.002 or risk>0.03:return None
    active=stop; best=entry; partial=False; realized=0.; remaining=1.
    end=min(len(df),i+1+FORWARD)
    for k in range(i+1,end):
        lo=float(df.low.iloc[k]); hi=float(df.high.iloc[k]); close=float(df.close.iloc[k])
        if direction>0:
            if lo<=active:
                ret=(active/entry-1)*100-FEE_SLIP_PCT
                return realized+remaining*ret,'stop_or_trail',k
            best=max(best,hi)
            if not partial and hi>=entry*(1+2*risk):
                realized += .5*((2*risk)*100-FEE_SLIP_PCT); remaining=.5; partial=True; active=max(active,entry)
            if partial:
                trail=float(df.low.iloc[max(i+1,k-4):k+1].min()); active=max(active,trail)
        else:
            if hi>=active:
                ret=(entry/active-1)*100-FEE_SLIP_PCT
                return realized+remaining*ret,'stop_or_trail',k
            best=min(best,lo)
            if not partial and lo<=entry*(1-2*risk):
                realized += .5*((2*risk)*100-FEE_SLIP_PCT); remaining=.5; partial=True; active=min(active,entry)
            if partial:
                trail=float(df.high.iloc[max(i+1,k-4):k+1].max()); active=min(active,trail)
        # pattern invalidation proxy: adverse close beyond 1R
        if direction>0 and close<=entry*(1-risk):
            ret=(close/entry-1)*100-FEE_SLIP_PCT; return realized+remaining*ret,'pattern_invalid',k
        if direction<0 and close>=entry*(1+risk):
            ret=(entry/close-1)*100-FEE_SLIP_PCT; return realized+remaining*ret,'pattern_invalid',k
    exitp=float(df.close.iloc[end-1])
    ret=((exitp/entry-1) if direction>0 else (entry/exitp-1))*100-FEE_SLIP_PCT
    return realized+remaining*ret,'time_exit',end-1


def summarize(t):
    if t.empty:return pd.DataFrame([{'trades':0}])
    r=t.net_pct.astype(float); gp=r[r>0].sum(); gl=-r[r<0].sum(); eq=100.;peak=100.;mdd=0.
    for x in r:
        eq*=max(0,1+RISK_PER_TRADE*(x/max(t.risk_pct.median(),0.01)))
        peak=max(peak,eq);mdd=max(mdd,(peak-eq)/peak)
    return pd.DataFrame([{'trades':len(t),'win_rate_pct':(r>0).mean()*100,'avg_trade_pct':r.mean(),'median_trade_pct':r.median(),'profit_factor':gp/gl if gl>0 else np.inf,'mdd_pct':mdd*100,'ending_equity_proxy':eq,'avg_similarity':t.similarity.mean(),'avg_consensus':t.consensus.mean(),'longs':int((t.direction==1).sum()),'shorts':int((t.direction==-1).sum())}])


def main():
    end=pd.Timestamp(datetime.now(timezone.utc)); start=end-pd.Timedelta(days=DAYS+50)
    df=get_klines(int(start.timestamp()*1000),int(end.timestamp()*1000))
    rows=[]; i=LOOKBACK+HIST_WINDOW
    while i<len(df)-FORWARD-1:
        sig=choose_signal(df,i)
        if not sig:i+=4;continue
        trade=run_trade(df,i,sig)
        if not trade:i+=4;continue
        net,reason,k=trade
        entry=float(df.open.iloc[i+1])
        if sig['direction']>0: stop=float(df.low.iloc[i-8:i].min()); risk=(entry-max(stop,entry*(1-0.025)))/entry*100
        else: stop=float(df.high.iloc[i-8:i].max()); risk=(min(stop,entry*(1+0.025))-entry)/entry*100
        rows.append({'signal_time':df.index[i],'direction':sig['direction'],'similarity':sig['similarity'],'consensus':sig['consensus'],'median_future':sig['median_future'],'value_ratio':sig['value_ratio'],'risk_pct':risk,'net_pct':net,'exit_reason':reason,'exit_time':df.index[k]})
        i=max(i+4,k+1)
    t=pd.DataFrame(rows)
    if t.empty: raise RuntimeError('No trades produced')
    # only final 2/3 of downloaded sample is evaluation; earlier period supplies templates
    cutoff=df.index[int(len(df)*.33)]
    ev=t[pd.to_datetime(t.signal_time,utc=True)>=cutoff].copy()
    ev.to_csv('wonyotti_inspired_trades.csv',index=False)
    s=summarize(ev);s.insert(0,'evaluation_start',cutoff);s.insert(1,'evaluation_end',df.index[-1]);s.to_csv('wonyotti_inspired_summary.csv',index=False)
    ev['month']=pd.to_datetime(ev.signal_time,utc=True).dt.to_period('M').astype(str)
    ev.groupby('month').agg(trades=('net_pct','size'),avg_pct=('net_pct','mean'),sum_pct=('net_pct','sum'),win_rate_pct=('net_pct',lambda x:(x>0).mean()*100)).reset_index().to_csv('wonyotti_inspired_monthly.csv',index=False)
    print(s.to_string(index=False),flush=True)

if __name__=='__main__':main()
