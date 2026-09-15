"""Fast all-KRW surge reverse-trace research for Catch World.
Research only; no orders. Finds surge days first across every KRW market, then downloads
5m data only around those events and measures 6/12/24/72h pre-surge money-flow changes.
"""
from __future__ import annotations
import time
from datetime import datetime, timezone
from pathlib import Path
import numpy as np
import pandas as pd
import requests

BASE='https://api.upbit.com/v1'
OUT=Path('results_daily_surge'); OUT.mkdir(exist_ok=True)
DAYS=90
BAR=5
SURGES=(0.05,0.10,0.20)


def get(path,params=None,retries=6):
    for k in range(retries):
        try:
            r=requests.get(BASE+path,params=params,timeout=30,headers={'User-Agent':'CatchWorld-SurgeReverseTrace'})
            if r.status_code==429:
                time.sleep(0.4*(k+1)); continue
            r.raise_for_status(); time.sleep(0.11); return r.json()
        except Exception:
            if k==retries-1: raise
            time.sleep(0.6*(k+1))


def markets():
    return [x['market'] for x in get('/market/all',{'is_details':'false'}) if x['market'].startswith('KRW-')]


def daily(m,end):
    js=get('/candles/days',{'market':m,'count':min(DAYS+5,200),'to':end.strftime('%Y-%m-%dT%H:%M:%SZ')})
    if not js:return pd.DataFrame()
    d=pd.DataFrame(js); d['time']=pd.to_datetime(d.candle_date_time_utc,utc=True)
    d=d.sort_values('time').set_index('time')
    for c,src in [('open','opening_price'),('high','high_price'),('low','low_price'),('close','trade_price'),('value','candle_acc_trade_price'),('volume','candle_acc_trade_volume')]: d[c]=pd.to_numeric(d[src])
    return d


def find_events(m,d):
    out=[]
    if len(d)<3:return out
    # Intraday surge from daily open to high; no turnover ranking filter.
    for t,r in d.iloc[-DAYS:].iterrows():
        move=float(r.high/r.open-1) if r.open else 0
        hit=max([x for x in SURGES if move>=x],default=None)
        if hit is not None: out.append((m,t,move,hit))
    return out


def candles5(m,start,end):
    rows=[]; to=end+pd.Timedelta(minutes=BAR)
    while to>start:
        js=get(f'/candles/minutes/{BAR}',{'market':m,'count':200,'to':to.strftime('%Y-%m-%dT%H:%M:%SZ')})
        if not js:break
        rows+=js; old=pd.Timestamp(js[-1]['candle_date_time_utc'],tz='UTC')
        if old<=start:break
        to=old-pd.Timedelta(seconds=1)
    if not rows:return pd.DataFrame()
    d=pd.DataFrame(rows); d['time']=pd.to_datetime(d.candle_date_time_utc,utc=True)
    d=d.drop_duplicates('time').set_index('time').sort_index().loc[start:end]
    for c,src in [('open','opening_price'),('high','high_price'),('low','low_price'),('close','trade_price'),('value','candle_acc_trade_price'),('volume','candle_acc_trade_volume')]: d[c]=pd.to_numeric(d[src])
    return d


def summarize(m,day,move,hit,x):
    # day is 00:00 UTC; Upbit daily boundary is 09:00 KST. Use event-day start as reference.
    ref=day
    pre=x[x.index<ref]
    if pre.empty:return None
    row={'market':m,'event_utc':ref.isoformat(),'event_kst':ref.tz_convert('Asia/Seoul').isoformat(),'day_open_to_high_pct':move*100,'surge_bucket_pct':int(hit*100)}
    base=pre[(pre.index>=ref-pd.Timedelta(hours=72))&(pre.index<ref-pd.Timedelta(hours=24))]
    base_hour=(base.value.sum()/48.0) if len(base) else np.nan
    for h in (6,12,24,72):
        z=pre[pre.index>=ref-pd.Timedelta(hours=h)]
        row[f'value_{h}h']=float(z.value.sum())
        row[f'volume_{h}h']=float(z.volume.sum())
        row[f'ret_{h}h_pct']=float((z.close.iloc[-1]/z.open.iloc[0]-1)*100) if len(z) else np.nan
        hourly=float(z.value.sum()/h) if len(z) else np.nan
        row[f'value_rate_{h}h_vs_base']=float(hourly/base_hour) if np.isfinite(base_hour) and base_hour>0 else np.nan
    return row


def main():
    end=pd.Timestamp(datetime.now(timezone.utc)).floor('min')
    ms=markets(); events=[]
    print('KRW markets',len(ms),flush=True)
    for i,m in enumerate(ms,1):
        try: events.extend(find_events(m,daily(m,end)))
        except Exception as e: print('daily skip',m,e,flush=True)
        if i%25==0: print('daily scan',i,'/',len(ms),'events',len(events),flush=True)
    ev=pd.DataFrame(events,columns=['market','event_utc','move','bucket'])
    ev.to_csv(OUT/'surge_events_all_krw.csv',index=False)
    print('surge events',len(events),flush=True)

    rows=[]
    for i,(m,t,move,hit) in enumerate(events,1):
        try:
            x=candles5(m,t-pd.Timedelta(hours=74),t+pd.Timedelta(hours=8))
            r=summarize(m,t,move,hit,x)
            if r:rows.append(r)
        except Exception as e: print('detail skip',m,t,e,flush=True)
        if i%20==0: print('reverse trace',i,'/',len(events),flush=True)
    df=pd.DataFrame(rows); df.to_csv(OUT/'daily_surge_samples.csv',index=False)
    if df.empty: raise RuntimeError('no reverse-trace samples')
    metrics=[]
    for bucket in (5,10,20):
        s=df[df.surge_bucket_pct>=bucket]
        if s.empty:continue
        r={'surge_pct':bucket,'events':len(s)}
        for h in (6,12,24,72):
            col=f'value_rate_{h}h_vs_base'; r[f'median_value_rate_{h}h']=float(s[col].median()); r[f'p75_value_rate_{h}h']=float(s[col].quantile(.75)); r[f'median_price_ret_{h}h_pct']=float(s[f'ret_{h}h_pct'].median())
        metrics.append(r)
    pd.DataFrame(metrics).to_csv(OUT/'daily_surge_metrics.csv',index=False)
    # compatibility artifacts
    df.sort_values('day_open_to_high_pct',ascending=False).head(300).to_csv(OUT/'daily_surge_top3_daily.csv',index=False)
    df.sort_values('event_utc').to_csv(OUT/'daily_surge_first_detection.csv',index=False)
    print(pd.DataFrame(metrics).to_string(index=False),flush=True)

if __name__=='__main__': main()
