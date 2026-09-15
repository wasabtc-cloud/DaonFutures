"""CatchWorld BLUE-B false-signal filter research.
Research only: compares successful/failed B-like setups on focused 1m artifacts.
"""
from pathlib import Path
import pandas as pd
import numpy as np

OUT=Path('results_blue_b_filter'); OUT.mkdir(exist_ok=True)
FILES={'ASTR':'results_capital_lifecycle/astr_1m_features.csv','ZIL':'results_capital_lifecycle/zil_1m_features.csv','TREE':'results_capital_lifecycle/tree_1m_features.csv'}
rows=[]
for coin,path in FILES.items():
    p=Path(path)
    if not p.exists(): continue
    x=pd.read_csv(p)
    # tolerate current artifact naming
    close_col=next((c for c in ['close','trade_price'] if c in x),None)
    if close_col is None: continue
    close=x[close_col].astype(float)
    ret=close.pct_change()
    ema20=close.ewm(span=20,adjust=False).mean(); ema60=close.ewm(span=60,adjust=False).mean()
    d=close.diff(); gain=d.clip(lower=0).rolling(14).mean(); loss=(-d.clip(upper=0)).rolling(14).mean(); rsi=100-100/(1+gain/loss.replace(0,np.nan))
    vcol=next((c for c in ['candle_acc_trade_price','trade_value','value'] if c in x),None)
    if vcol is None: continue
    v=x[vcol].astype(float); vr=v.rolling(60).sum()/v.rolling(1440,min_periods=120).mean().mul(60)
    hi=x[next((c for c in ['high','high_price'] if c in x),close_col)].astype(float)
    lo=x[next((c for c in ['low','low_price'] if c in x),close_col)].astype(float)
    tr=pd.concat([(hi-lo),(hi-close.shift()).abs(),(lo-close.shift()).abs()],axis=1).max(axis=1)
    atr=tr.rolling(14).mean()/close
    mid=close.rolling(20).mean(); sd=close.rolling(20).std(); bbw=(4*sd/mid)
    future_max=close[::-1].rolling(360,min_periods=1).max()[::-1]/close-1
    # B-family grid: whale persistence/re-inflow + trend recovery + RSI + compression
    for vr_min in [2,3,5,8]:
      for rsi_min in [45,50,55]:
       for bbw_max in [0.03,0.05,0.08]:
        sig=(vr>=vr_min)&(close>=ema20)&(ema20>=ema60*0.995)&(rsi>=rsi_min)&(bbw<=bbw_max)&(atr<=0.03)
        idx=np.flatnonzero(sig.fillna(False).to_numpy())
        # de-duplicate signals within 60m
        keep=[]; last=-999
        for i in idx:
            if i-last>=60: keep.append(i); last=i
        if not keep: continue
        f=future_max.iloc[keep]
        rows.append({'coin':coin,'vr_min':vr_min,'rsi_min':rsi_min,'bbw_max':bbw_max,'signals':len(keep),'hit10':float((f>=.10).mean()),'hit20':float((f>=.20).mean()),'avg_mfe6h':float(f.mean())})
res=pd.DataFrame(rows)
res.to_csv(OUT/'blue_b_filter_grid.csv',index=False)
if not res.empty:
    agg=res.groupby(['vr_min','rsi_min','bbw_max']).agg(signals=('signals','sum'),hit10=('hit10','mean'),hit20=('hit20','mean'),avg_mfe6h=('avg_mfe6h','mean')).reset_index()
    agg=agg.sort_values(['hit20','hit10','avg_mfe6h'],ascending=False)
    agg.to_csv(OUT/'blue_b_filter_summary.csv',index=False)
    print(agg.head(20).to_string(index=False))
else: print('No usable focused artifacts found')
