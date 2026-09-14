"""Historical research for pre-surge patterns in Upbit KRW markets.
Research only. No orders, portfolio actions, or live trading decisions.
"""
from __future__ import annotations
import time
from datetime import datetime, timezone
from pathlib import Path
import numpy as np
import pandas as pd
import requests

BASE='https://api.upbit.com/v1'
OUT=Path('results_whale_memory'); OUT.mkdir(exist_ok=True)
BAR=15
EVAL_DAYS=30
LOOKBACK_DAYS=10
S=requests.Session(); S.headers.update({'User-Agent':'CatchWorld-WhaleMemory-Research'})

def get(path,params=None,retries=6):
    for k in range(retries):
        try:
            r=S.get(BASE+path,params=params,timeout=30)
            if r.status_code==429:
                time.sleep(.5*(k+1)); continue
            r.raise_for_status(); time.sleep(.12); return r.json()
        except Exception:
            if k==retries-1: raise
            time.sleep(.7*(k+1))

def markets():
    return [x['market'] for x in get('/market/all',{'is_details':'false'}) if x['market'].startswith('KRW-')]

def candles(m,start,end):
    rows=[]; to=end+pd.Timedelta(minutes=BAR)
    while to>start:
        js=get(f'/candles/minutes/{BAR}',{'market':m,'count':200,'to':to.strftime('%Y-%m-%dT%H:%M:%SZ')})
        if not js: break
        rows+=js
        old=pd.Timestamp(js[-1]['candle_date_time_utc'],tz='UTC')
        if old<=start: break
        to=old-pd.Timedelta(seconds=1)
    if not rows:return pd.DataFrame()
    d=pd.DataFrame(rows); d['time']=pd.to_datetime(d.candle_date_time_utc,utc=True)
    d=d.drop_duplicates('time').set_index('time').sort_index().loc[start:end]
    out=pd.DataFrame(index=d.index)
    for a,b in [('open','opening_price'),('high','high_price'),('low','low_price'),('close','trade_price'),('value','candle_acc_trade_price')]:
        out[a]=pd.to_numeric(d[b],errors='coerce')
    return out.dropna()

def enrich(d,btc):
    x=d.copy(); h=4; h4=16; d1=96; d3=288
    x['ret1h']=x.close.pct_change(h); x['ret4h']=x.close.pct_change(h4); x['ret24h']=x.close.pct_change(d1)
    v1=x.value.rolling(h).sum(); v4=x.value.rolling(h4).sum(); v24=x.value.rolling(d1).sum()
    b1=v1.shift(h).rolling(7*d1,min_periods=2*d1).median()
    b4=v4.shift(h4).rolling(7*d1,min_periods=2*d1).median()
    b24=v24.shift(d1).rolling(7*d1,min_periods=2*d1).median()
    x['vr1h']=v1/(b1+1e-12); x['vr4h']=v4/(b4+1e-12); x['vr24h']=v24/(b24+1e-12)
    x['whale72h']=x.vr1h.shift(1).rolling(d3,min_periods=d1).max()
    x['range4h']=x.high.rolling(h4).max()/x.low.rolling(h4).min()-1
    x['absorption']=x.vr24h/(1+12*x.ret24h.abs())
    b=btc[['close']].rename(columns={'close':'btc'}).reindex(x.index).ffill(); x=x.join(b)
    x['btc24h']=x.btc.pct_change(d1); x['rel24h']=x.ret24h-x.btc24h
    fmax=x.high.shift(-1)[::-1].rolling(24,min_periods=1).max()[::-1]
    x['fwd6h']=fmax/x.open.shift(-1)-1
    x['surge20']=(x.fwd6h>=.20).astype(int)
    return x

def main():
    end=pd.Timestamp(datetime.now(timezone.utc)).floor('15min')
    eval_start=end-pd.Timedelta(days=EVAL_DAYS); start=eval_start-pd.Timedelta(days=LOOKBACK_DAYS)
    btc=candles('KRW-BTC',start,end)
    parts=[]
    for i,m in enumerate(markets(),1):
        print(i,m,flush=True)
        try:
            d=candles(m,start,end)
            if len(d)<700: continue
            x=enrich(d,btc); x['market']=m; x=x.loc[x.index>=eval_start]
            parts.append(x[x.index.minute.eq(0)])
        except Exception as e: print('skip',m,e,flush=True)
    z=pd.concat(parts).replace([np.inf,-np.inf],np.nan)
    z.reset_index(names='time_utc').to_csv(OUT/'whale_memory_samples.csv',index=False)
    feats=['vr1h','vr4h','vr24h','whale72h','absorption','rel24h','range4h']
    base=z.surge20.mean(); rows=[]
    for f in feats:
        q=z[[f,'surge20']].dropna()
        for p in (.8,.9,.95,.97,.99):
            th=q[f].quantile(p); s=q[q[f]>=th]
            if len(s)<10: continue
            hit=s.surge20.mean()
            rows.append({'feature':f,'quantile':p,'threshold':th,'samples':len(s),'surge20_rate_pct':hit*100,'base_rate_pct':base*100,'lift':hit/(base+1e-12)})
    r=pd.DataFrame(rows).sort_values('lift',ascending=False)
    r.to_csv(OUT/'whale_memory_feature_lifts.csv',index=False)
    print(r.head(30).to_string(index=False),flush=True)

if __name__=='__main__': main()
