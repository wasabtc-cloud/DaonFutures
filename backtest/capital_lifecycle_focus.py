"""Focused CatchWorld research: ASTR/ZIL/TREE pre-surge capital lifecycle.
Research only; no orders or live trading decisions.
"""
from __future__ import annotations
import time
from datetime import datetime, timezone
from pathlib import Path
import numpy as np
import pandas as pd
import requests

BASE='https://api.upbit.com/v1'
MARKETS=['KRW-ASTR','KRW-ZIL','KRW-TREE']
OUT=Path('results_capital_lifecycle'); OUT.mkdir(exist_ok=True)
S=requests.Session(); S.headers.update({'User-Agent':'CatchWorld-CapitalLifecycle-Research'})

def get(path,params=None,retries=6):
    for k in range(retries):
        try:
            r=S.get(BASE+path,params=params,timeout=30)
            if r.status_code==429:
                time.sleep(.5*(k+1)); continue
            r.raise_for_status(); time.sleep(.13); return r.json()
        except Exception:
            if k==retries-1: raise
            time.sleep(.8*(k+1))

def candles(m,days=14):
    end=pd.Timestamp(datetime.now(timezone.utc)).floor('min'); start=end-pd.Timedelta(days=days)
    rows=[]; to=end+pd.Timedelta(minutes=1)
    while to>start:
        js=get('/candles/minutes/1',{'market':m,'count':200,'to':to.strftime('%Y-%m-%dT%H:%M:%SZ')})
        if not js: break
        rows += js
        old=pd.Timestamp(js[-1]['candle_date_time_utc'],tz='UTC')
        if old<=start: break
        to=old-pd.Timedelta(seconds=1)
    d=pd.DataFrame(rows); d['time']=pd.to_datetime(d.candle_date_time_utc,utc=True)
    d=d.drop_duplicates('time').set_index('time').sort_index().loc[start:end]
    x=pd.DataFrame(index=d.index)
    x['open']=pd.to_numeric(d.opening_price); x['high']=pd.to_numeric(d.high_price)
    x['low']=pd.to_numeric(d.low_price); x['close']=pd.to_numeric(d.trade_price)
    x['value']=pd.to_numeric(d.candle_acc_trade_price); x['volume']=pd.to_numeric(d.candle_acc_trade_volume)
    return x

def features(x):
    z=x.copy(); h=60; h4=240; d1=1440
    z['v1h']=z.value.rolling(h,min_periods=20).sum(); z['v4h']=z.value.rolling(h4,min_periods=60).sum()
    z['base1h']=z.v1h.shift(h).rolling(3*d1,min_periods=d1).median()
    z['vr1h']=z.v1h/(z.base1h+1e-12)
    z['ret1h']=z.close.pct_change(h); z['ret4h']=z.close.pct_change(h4); z['ret24h']=z.close.pct_change(d1)
    z['defense4h']=z.close/z.low.rolling(h4,min_periods=60).min()-1
    z['range4h']=z.high.rolling(h4,min_periods=60).max()/z.low.rolling(h4,min_periods=60).min()-1
    z['absorption']=z.vr1h/(1+20*z.ret4h.abs())
    z['seed']=z.vr1h>=z.vr1h.quantile(.97)
    # Capital memory does not expire by age alone: track most recent seed and evidence after it.
    seed_time=pd.Series(pd.NaT,index=z.index,dtype='datetime64[ns, UTC]')
    seed_time.loc[z.seed]=z.index[z.seed]; z['seed_time']=seed_time.ffill()
    z['age_h']=(pd.Series(z.index,index=z.index)-z.seed_time).dt.total_seconds()/3600
    z['re_inflow']=z.seed & (z.age_h>1)
    z['ignition']=(z.vr1h>=z.vr1h.quantile(.99)) & (z.ret1h>0) & (z.close>=z.high.rolling(h4,min_periods=60).max().shift(1)*.98)
    z['exit_risk']=(z.vr1h>=z.vr1h.quantile(.95)) & (z.ret1h<-.03)
    return z

def summarize(m,z):
    q=z.dropna(subset=['vr1h']).copy(); top=q.nlargest(30,'vr1h')
    rows=[]
    for t,r in top.iterrows():
        future=q.loc[t:t+pd.Timedelta(hours=24)]
        past=q.loc[max(q.index.min(),t-pd.Timedelta(days=7)):t]
        rows.append({'market':m,'time_utc':t,'vr1h':r.vr1h,'ret1h':r.ret1h,'ret4h':r.ret4h,
                     'absorption':r.absorption,'max_next24h':future.high.max()/r.close-1 if len(future) else np.nan,
                     'max_drawdown_next24h':future.low.min()/r.close-1 if len(future) else np.nan,
                     'prior7d_max_vr1h':past.vr1h.max() if len(past) else np.nan})
    return pd.DataFrame(rows)

def main():
    summaries=[]
    for m in MARKETS:
        print('fetch',m,flush=True); x=candles(m,14); z=features(x)
        z.reset_index(names='time_utc').to_csv(OUT/f'{m[4:].lower()}_1m_features.csv',index=False)
        summaries.append(summarize(m,z))
    s=pd.concat(summaries,ignore_index=True).sort_values(['market','vr1h'],ascending=[True,False])
    s.to_csv(OUT/'astr_zil_tree_capital_events.csv',index=False)
    print(s.groupby('market')[['vr1h','max_next24h','max_drawdown_next24h']].head(10).to_string(index=False),flush=True)

if __name__=='__main__': main()
