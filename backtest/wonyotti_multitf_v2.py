"""Research-only Wonyotti-inspired multi-timeframe backtest v2.

NOT a reproduction of any private/proprietary method. This operationalizes only publicly
reported high-level ideas: compare candle+volume patterns on the SAME timeframe, consult
multiple common timeframes, use BTC market context, exit on pattern invalidation, and
manage risk. No live orders are placed.

Timeframes: 1m, 5m, 15m, 1h, 4h, 1d.
Each timeframe builds its own pattern vector and compares only against historical vectors
from that same timeframe. We then combine directional votes. Several fixed timeframe
combinations are tested without parameter tuning. The final 40% of the sample is OOS.
"""
from __future__ import annotations
import time, math, requests
import numpy as np
import pandas as pd
from datetime import datetime, timezone

BASE='https://api.upbit.com/v1'
MARKET='KRW-BTC'
TOTAL_DAYS=240
EVAL_STEP_MIN=30
FEE_SLIP_PCT=0.12
RISK_PER_TRADE=0.01
K=9
MIN_SIM=0.84
MIN_CONSENSUS=0.67
MIN_TF_VALID=3

TF_CFG={
    '1m':  {'rule':'1min',  'lookback':20,'future':30, 'hist_days':30,'sample_every':15,'weight':1.0},
    '5m':  {'rule':'5min',  'lookback':16,'future':12, 'hist_days':45,'sample_every':3, 'weight':1.2},
    '15m': {'rule':'15min', 'lookback':12,'future':8,  'hist_days':60,'sample_every':1, 'weight':1.3},
    '1h':  {'rule':'1h',    'lookback':12,'future':6,  'hist_days':90,'sample_every':1, 'weight':1.4},
    '4h':  {'rule':'4h',    'lookback':8, 'future':6,  'hist_days':120,'sample_every':1, 'weight':1.2},
    '1d':  {'rule':'1D',    'lookback':6, 'future':3,  'hist_days':180,'sample_every':1, 'weight':0.9},
}

VARIANTS={
    'FAST_1m_5m_15m':['1m','5m','15m'],
    'CORE_5m_15m_1h':['5m','15m','1h'],
    'MID_15m_1h_4h':['15m','1h','4h'],
    'FULL_1m_5m_15m_1h_4h_1d':['1m','5m','15m','1h','4h','1d'],
    'FULL_NO_1m':['5m','15m','1h','4h','1d'],
}


def fetch_1m(start:pd.Timestamp,end:pd.Timestamp)->pd.DataFrame:
    rows=[]
    to=end+pd.Timedelta(minutes=1)
    while to>start:
        r=requests.get(BASE+'/candles/minutes/1',params={
            'market':MARKET,'count':200,'to':to.strftime('%Y-%m-%dT%H:%M:%SZ')
        },timeout=30,headers={'User-Agent':'DaonFutures-Wonyotti-MTF-v2'})
        if r.status_code==429:
            time.sleep(.5); continue
        r.raise_for_status(); js=r.json()
        if not js: break
        rows.extend(js)
        oldest=pd.Timestamp(js[-1]['candle_date_time_utc'],tz='UTC')
        if oldest<=start: break
        to=oldest-pd.Timedelta(seconds=1)
        time.sleep(.12)
    d=pd.DataFrame(rows)
    if d.empty: return d
    d['time']=pd.to_datetime(d.candle_date_time_utc,utc=True)
    d=d.drop_duplicates('time').set_index('time').sort_index()
    d=d.loc[(d.index>=start)&(d.index<=end)]
    out=pd.DataFrame(index=d.index)
    out['open']=pd.to_numeric(d.opening_price)
    out['high']=pd.to_numeric(d.high_price)
    out['low']=pd.to_numeric(d.low_price)
    out['close']=pd.to_numeric(d.trade_price)
    out['volume']=pd.to_numeric(d.candle_acc_trade_volume)
    out['qv']=pd.to_numeric(d.candle_acc_trade_price)
    return out


def resample_ohlcv(df:pd.DataFrame,rule:str)->pd.DataFrame:
    if rule=='1min': return df.copy()
    o=df.open.resample(rule,label='right',closed='right').first()
    h=df.high.resample(rule,label='right',closed='right').max()
    l=df.low.resample(rule,label='right',closed='right').min()
    c=df.close.resample(rule,label='right',closed='right').last()
    v=df.volume.resample(rule,label='right',closed='right').sum()
    q=df.qv.resample(rule,label='right',closed='right').sum()
    z=pd.concat([o,h,l,c,v,q],axis=1)
    z.columns=['open','high','low','close','volume','qv']
    return z.dropna()


def pattern_vec(w:pd.DataFrame)->np.ndarray:
    o=w.open.values.astype(float); h=w.high.values.astype(float)
    l=w.low.values.astype(float); c=w.close.values.astype(float)
    q=w.qv.values.astype(float)
    base=np.maximum(o,1e-12)
    body=(c-o)/base
    upper=(h-np.maximum(o,c))/base
    lower=(np.minimum(o,c)-l)/base
    ret=np.diff(np.log(np.maximum(c,1e-12)),prepend=np.log(max(c[0],1e-12)))
    qn=np.log1p(q/(np.median(q)+1e-12))
    x=np.r_[body,upper,lower,ret,qn]
    x=(x-x.mean())/(x.std()+1e-12)
    return x.astype(np.float32)


def tf_signal(df:pd.DataFrame,t:pd.Timestamp,cfg:dict):
    # strictly use bars completed by t
    sub=df.loc[:t]
    lb=cfg['lookback']; fut=cfg['future']
    if len(sub)<lb+fut+20: return None
    i=len(sub)-1
    now=pattern_vec(sub.iloc[i-lb+1:i+1])
    hist_start=t-pd.Timedelta(days=cfg['hist_days'])
    h0=max(lb, int(np.searchsorted(sub.index.values, hist_start.to_datetime64())))
    last=i-fut-1
    if last<=h0: return None
    js=np.arange(h0,last,cfg['sample_every'])
    # cap candidate count to keep v2 tractable while preserving recency
    if len(js)>4500: js=js[-4500:]
    vecs=[]; rets=[]
    for j in js:
        try:
            x=pattern_vec(sub.iloc[j-lb+1:j+1])
        except Exception:
            continue
        if x.shape!=now.shape: continue
        future=float(sub.close.iloc[j+fut]/sub.close.iloc[j]-1)
        vecs.append(x); rets.append(future)
    if len(vecs)<K: return None
    M=np.vstack(vecs)
    denom=np.linalg.norm(M,axis=1)*max(np.linalg.norm(now),1e-12)
    sims=(M@now)/(denom+1e-12)
    good=np.where(sims>=MIN_SIM)[0]
    if len(good)<K: return None
    order=good[np.argsort(sims[good])[-K:]]
    fw=np.array(rets)[order]
    direction=1 if np.median(fw)>0 else -1
    consensus=float((np.sign(fw)==direction).mean())
    if consensus<MIN_CONSENSUS: return None
    q_recent=float(sub.qv.iloc[max(0,i-7):i+1].sum())
    q_roll=sub.qv.rolling(8).sum().iloc[max(0,i-100):i]
    q_base=float(q_roll.median()) if len(q_roll.dropna()) else np.nan
    value_ratio=q_recent/(q_base+1e-12) if np.isfinite(q_base) else 0.0
    return {'direction':direction,'consensus':consensus,'similarity':float(sims[order].mean()),
            'median_future':float(np.median(fw)),'value_ratio':float(value_ratio)}


def combine(signals:dict,names:list[str]):
    valid=[]
    for n in names:
        s=signals.get(n)
        if s is not None: valid.append((n,s))
    req=min(MIN_TF_VALID,len(names))
    if len(valid)<req: return None
    num=0.; den=0.; agree=[]
    for n,s in valid:
        w=TF_CFG[n]['weight']*max(0.25,s['consensus'])*max(0.25,s['similarity'])
        num+=w*s['direction']; den+=w; agree.append(s['direction'])
    score=num/(den+1e-12)
    direction=1 if score>0 else -1
    agreement=float((np.array(agree)==direction).mean())
    if abs(score)<0.22 or agreement<0.60: return None
    return {'direction':direction,'mtf_score':float(score),'agreement':agreement,'valid_tfs':len(valid)}


def run_trade(df1:pd.DataFrame,t:pd.Timestamp,sig:dict):
    # enter next 1m open; structural stop uses prior 30m, max 2.5%; hold max 8h
    pos=df1.index.searchsorted(t,side='right')
    if pos>=len(df1): return None
    entry=float(df1.open.iloc[pos]); direction=sig['direction']
    pre=df1.iloc[max(0,pos-30):pos]
    if len(pre)<10:return None
    if direction>0:
        structural=float(pre.low.min()); stop=max(structural,entry*(1-0.025)); risk=(entry-stop)/entry
    else:
        structural=float(pre.high.max()); stop=min(structural,entry*(1+0.025)); risk=(stop-entry)/entry
    if risk<0.002 or risk>0.03:return None
    active=stop; partial=False; realized=0.; remaining=1.
    end=min(len(df1),pos+480)
    for k in range(pos,end):
        lo=float(df1.low.iloc[k]); hi=float(df1.high.iloc[k]); close=float(df1.close.iloc[k])
        if direction>0:
            if lo<=active:
                ret=(active/entry-1)*100-FEE_SLIP_PCT
                return realized+remaining*ret,'stop_or_trail',k,risk*100
            if not partial and hi>=entry*(1+2*risk):
                realized+=.5*((2*risk)*100-FEE_SLIP_PCT); remaining=.5; partial=True; active=max(active,entry)
            if partial:
                trail=float(df1.low.iloc[max(pos,k-20):k+1].min()); active=max(active,trail)
        else:
            if hi>=active:
                ret=(entry/active-1)*100-FEE_SLIP_PCT
                return realized+remaining*ret,'stop_or_trail',k,risk*100
            if not partial and lo<=entry*(1-2*risk):
                realized+=.5*((2*risk)*100-FEE_SLIP_PCT); remaining=.5; partial=True; active=min(active,entry)
            if partial:
                trail=float(df1.high.iloc[max(pos,k-20):k+1].max()); active=min(active,trail)
        # close-based 1R invalidation
        if direction>0 and close<=entry*(1-risk):
            ret=(close/entry-1)*100-FEE_SLIP_PCT
            return realized+remaining*ret,'pattern_invalid',k,risk*100
        if direction<0 and close>=entry*(1+risk):
            ret=(entry/close-1)*100-FEE_SLIP_PCT
            return realized+remaining*ret,'pattern_invalid',k,risk*100
    exitp=float(df1.close.iloc[end-1])
    ret=((exitp/entry-1) if direction>0 else (entry/exitp-1))*100-FEE_SLIP_PCT
    return realized+remaining*ret,'time_exit',end-1,risk*100


def metrics(g:pd.DataFrame):
    if g.empty:return {'trades':0}
    r=g.net_pct.astype(float); gp=r[r>0].sum(); gl=-r[r<0].sum()
    eq=100.; peak=100.; mdd=0.
    for _,row in g.iterrows():
        rp=max(float(row.risk_pct),0.01)
        eq*=max(0,1+RISK_PER_TRADE*(float(row.net_pct)/rp))
        peak=max(peak,eq); mdd=max(mdd,(peak-eq)/peak)
    return {
        'trades':len(g),'win_rate_pct':float((r>0).mean()*100),'avg_trade_pct':float(r.mean()),
        'median_trade_pct':float(r.median()),'profit_factor':float(gp/gl) if gl>0 else np.inf,
        'mdd_pct':float(mdd*100),'ending_equity_proxy':float(eq),
        'avg_agreement':float(g.agreement.mean()),'avg_mtf_score_abs':float(g.mtf_score.abs().mean()),
        'longs':int((g.direction==1).sum()),'shorts':int((g.direction==-1).sum())
    }


def main():
    end=pd.Timestamp(datetime.now(timezone.utc)).floor('min')
    start=end-pd.Timedelta(days=TOTAL_DAYS)
    print('FETCH 1m',start,end,flush=True)
    df1=fetch_1m(start,end)
    if len(df1)<50000: raise RuntimeError(f'Not enough 1m candles: {len(df1)}')
    print('1m rows',len(df1),df1.index.min(),df1.index.max(),flush=True)
    frames={n:resample_ohlcv(df1,c['rule']) for n,c in TF_CFG.items()}
    for n,d in frames.items(): print('TF',n,len(d),flush=True)

    # Need enough history for the slowest timeframe; practical signal evaluation begins after 70d.
    eval_start=start+pd.Timedelta(days=70)
    times=pd.date_range(eval_start,end-pd.Timedelta(hours=8),freq=f'{EVAL_STEP_MIN}min',tz='UTC')
    rows=[]
    next_free={v:pd.Timestamp.min.tz_localize('UTC') for v in VARIANTS}
    for ix,t in enumerate(times):
        signals={n:tf_signal(d,t,TF_CFG[n]) for n,d in frames.items()}
        for v,names in VARIANTS.items():
            if t<next_free[v]: continue
            cs=combine(signals,names)
            if cs is None: continue
            tr=run_trade(df1,t,cs)
            if tr is None: continue
            net,reason,k,risk_pct=tr
            exit_time=df1.index[k]
            rows.append({'variant':v,'signal_time':t,'exit_time':exit_time,'direction':cs['direction'],
                         'mtf_score':cs['mtf_score'],'agreement':cs['agreement'],'valid_tfs':cs['valid_tfs'],
                         'risk_pct':risk_pct,'net_pct':net,'exit_reason':reason})
            next_free[v]=exit_time
        if ix%100==0: print('PROGRESS',ix,'/',len(times),'rows',len(rows),flush=True)

    trades=pd.DataFrame(rows)
    if trades.empty: raise RuntimeError('No trades produced')
    trades.to_csv('wonyotti_mtf_v2_trades.csv',index=False)

    split_time=eval_start+(end-eval_start)*0.60
    out=[]
    for v in VARIANTS:
        g=trades[trades.variant==v].copy()
        ins=g[pd.to_datetime(g.signal_time,utc=True)<split_time]
        oos=g[pd.to_datetime(g.signal_time,utc=True)>=split_time]
        for label,x in [('IS',ins),('OOS',oos),('ALL',g)]:
            m=metrics(x); m.update({'variant':v,'segment':label,'segment_start':(eval_start if label!='OOS' else split_time),
                                    'segment_end':(split_time if label=='IS' else end)})
            out.append(m)
    summary=pd.DataFrame(out)
    summary.to_csv('wonyotti_mtf_v2_summary.csv',index=False)

    oos=trades[pd.to_datetime(trades.signal_time,utc=True)>=split_time].copy()
    oos['month']=pd.to_datetime(oos.signal_time,utc=True).dt.to_period('M').astype(str)
    monthly=oos.groupby(['variant','month']).agg(trades=('net_pct','size'),avg_pct=('net_pct','mean'),
        sum_pct=('net_pct','sum'),win_rate_pct=('net_pct',lambda x:(x>0).mean()*100)).reset_index()
    monthly.to_csv('wonyotti_mtf_v2_monthly.csv',index=False)

    # Timeframe ablation visibility: how often each same-TF signal exists and its raw direction.
    tf_rows=[]
    sample_times=times[::max(1,int(120/EVAL_STEP_MIN))]
    for t in sample_times:
        for n,d in frames.items():
            s=tf_signal(d,t,TF_CFG[n])
            if s: tf_rows.append({'time':t,'tf':n,**s})
    pd.DataFrame(tf_rows).to_csv('wonyotti_mtf_v2_tf_signals.csv',index=False)
    print(summary.to_string(index=False),flush=True)

if __name__=='__main__':
    main()
