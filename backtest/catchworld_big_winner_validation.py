"""CatchWorld big-winner validation.

Consumes shard CSVs downloaded/extracted into data/trade_strength/.
No future data is used for entry features. Outputs event outcomes and a summary.
"""
from pathlib import Path
import pandas as pd
import numpy as np

DATA=Path('data/trade_strength')
OUT=Path('results/big_winner'); OUT.mkdir(parents=True,exist_ok=True)
FEE_SIDE=0.0005
HORIZONS=[3,5,8,10,15,20]

def load_1m():
    fs=sorted(DATA.glob('trade_strength_7d_1m_shard_*.csv'))
    if not fs: raise FileNotFoundError('Put 1m shard CSVs in data/trade_strength/')
    d=pd.concat((pd.read_csv(f) for f in fs),ignore_index=True)
    # normalize common collector names
    ren={}
    for c in d.columns:
        lc=c.lower()
        if lc in ('timestamp','time','datetime','candle_date_time_utc'): ren[c]='time'
        elif lc in ('trade_price','close','price'): ren[c]='price'
    d=d.rename(columns=ren)
    d['time']=pd.to_datetime(d['time'],utc=True,errors='coerce')
    d=d.dropna(subset=['market','time']).sort_values(['market','time'])
    return d

def col(df,*names):
    for n in names:
        if n in df.columns:return n
    return None

def main():
    d=load_1m()
    p=col(d,'price','last_price')
    flow=col(d,'flow','trade_strength','buy_sell_ratio')
    buy=col(d,'buy_notional','bid_notional','buy_amount')
    sell=col(d,'sell_notional','ask_notional','sell_amount')
    if p is None: raise ValueError(f'price column missing: {list(d.columns)}')
    g=d.groupby('market',group_keys=False)
    d['ret30']=g[p].pct_change(30)*100
    # If collector has a native flow use it; otherwise derive buy/sell notional ratio.
    if flow is None:
        if buy is None or sell is None: raise ValueError(f'flow/buy/sell columns missing: {list(d.columns)}')
        d['flow_calc']=d[buy]/d[sell].replace(0,np.nan)
        flow='flow_calc'
    # Entry universe requested in research: Flow>=6 and -2.5..-2.0% 30m pullback.
    cand=d[(d[flow]>=6)&d['ret30'].between(-2.5,-2.0)].copy()
    # 60m same-market cooldown, causal.
    keep=[]; last={}
    for i,r in cand.iterrows():
        t=r.time; m=r.market
        if m not in last or (t-last[m]).total_seconds()>=3600:
            keep.append(i); last[m]=t
    cand=d.loc[keep].copy()
    # Future path is used only as outcome label, never as an entry feature.
    lookup=d.set_index(['market','time'])[p]
    rows=[]
    for _,r in cand.iterrows():
        m,t,ep=r.market,r.time,float(r[p])
        path=d[(d.market==m)&(d.time>t)&(d.time<=t+pd.Timedelta(hours=6))][['time',p]]
        if path.empty: continue
        rr=(path[p]/ep-1)*100
        o={'market':m,'entry_time':t,'entry_price':ep,'flow':r[flow],'ret30':r.ret30,
           'mfe6h':rr.max(),'mae6h':rr.min()}
        for x in HORIZONS:o[f'reach_{x}']=bool((rr>=x).any())
        for mins in (1,3,5,15,30,60,120,360):
            z=path[path.time<=t+pd.Timedelta(minutes=mins)]
            o[f'ret_{mins}m']=np.nan if z.empty else (float(z.iloc[-1][p])/ep-1)*100
        rows.append(o)
    ev=pd.DataFrame(rows)
    ev.to_csv(OUT/'events.csv',index=False)
    summary={'events':len(ev),'mfe6h_mean':ev.mfe6h.mean(),'mae6h_mean':ev.mae6h.mean()}
    for x in HORIZONS: summary[f'reach_{x}_pct']=100*ev[f'reach_{x}'].mean()
    pd.DataFrame([summary]).to_csv(OUT/'summary.csv',index=False)
    print(pd.DataFrame([summary]).to_string(index=False))

if __name__=='__main__':main()
