"""Research scanner for Upbit KRW markets around the 09:00 KST daily rollover.

Goal: identify pre-09:00 features (08:30-08:59 KST), record the actual daily
09:00-10:00 top-5 movers, and build simple profile summaries. Research only;
this code never places orders.
"""
from __future__ import annotations

import time
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd
import requests

BASE='https://api.upbit.com/v1'
OUT=Path('results_9am')
OUT.mkdir(exist_ok=True)
DAYS=180
TOP_MARKETS=30
THRESHOLDS=(0.05,0.10,0.15,0.20)
POST_WINDOW_MIN=60


def get(path,params=None,retries=6):
    for k in range(retries):
        try:
            r=requests.get(BASE+path,params=params,timeout=30,headers={'User-Agent':'DaonFutures-9AM-Scanner'})
            if r.status_code==429:
                time.sleep(0.35*(k+1)); continue
            r.raise_for_status(); return r.json()
        except Exception:
            if k==retries-1: raise
            time.sleep(0.5*(k+1))


def markets():
    return [x['market'] for x in get('/market/all',{'is_details':'false'}) if x['market'].startswith('KRW-')]


def candles_1m(market,start,end):
    rows=[]; to=end+pd.Timedelta(minutes=1)
    while to>start:
        js=get('/candles/minutes/1',{'market':market,'count':200,'to':to.strftime('%Y-%m-%dT%H:%M:%SZ')})
        if not js: break
        rows+=js
        old=pd.Timestamp(js[-1]['candle_date_time_utc'],tz='UTC')
        if old<=start: break
        to=old-pd.Timedelta(seconds=1)
    if not rows:return pd.DataFrame()
    d=pd.DataFrame(rows)
    d['time']=pd.to_datetime(d.candle_date_time_utc,utc=True)
    d=d.drop_duplicates('time').set_index('time').sort_index().loc[start:end]
    out=pd.DataFrame(index=d.index)
    for a,b in [('open','opening_price'),('high','high_price'),('low','low_price'),('close','trade_price'),('value','candle_acc_trade_price'),('volume','candle_acc_trade_volume')]:
        out[a]=pd.to_numeric(d[b])
    return out


def daily_value_rank(ms,anchor):
    vals=[]
    for i,m in enumerate(ms,1):
        try:
            js=get('/candles/days',{'market':m,'count':20,'to':anchor.strftime('%Y-%m-%dT%H:%M:%SZ')})
            if js:
                vals.append((m,float(np.mean([x['candle_acc_trade_price'] for x in js]))))
        except Exception: pass
        if i%50==0: print('rank',i,'/',len(ms),flush=True)
    return [m for m,_ in sorted(vals,key=lambda z:z[1],reverse=True)[:TOP_MARKETS]]


def first_cross_minutes(post,base_price,threshold):
    hit=post.index[post.high >= base_price*(1+threshold)]
    if len(hit)==0:return np.nan
    return float((hit[0]-post.index[0]).total_seconds()/60.0)


def feature_row(market,day_kst,raw):
    # Upbit daily rollover: 09:00 KST = 00:00 UTC.
    roll_utc=(pd.Timestamp(day_kst).tz_localize('Asia/Seoul')+pd.Timedelta(hours=9)).tz_convert('UTC')
    pre=raw.loc[(raw.index>=roll_utc-pd.Timedelta(minutes=30))&(raw.index<roll_utc)]
    post=raw.loc[(raw.index>=roll_utc)&(raw.index<=roll_utc+pd.Timedelta(minutes=POST_WINDOW_MIN))]
    hist=raw.loc[(raw.index>=roll_utc-pd.Timedelta(hours=6))&(raw.index<roll_utc-pd.Timedelta(minutes=30))]
    if len(pre)<20 or len(post)<40 or len(hist)<60:return None
    v5=pre.value.tail(5).sum(); pv5=pre.value.iloc[-10:-5].sum()
    base5=hist.value.rolling(5).sum().dropna().tail(36)
    base30=hist.value.rolling(30).sum().dropna().tail(12)
    p0=float(pre.close.iloc[0]); plast=float(pre.close.iloc[-1])
    post_open=float(post.open.iloc[0]); post_high=float(post.high.max())
    post_low=float(post.low.min())
    pre_high=float(pre.high.max())
    max_ret=post_high/post_open-1
    max_time=post.high.idxmax()
    result={
        'day_kst':str(pd.Timestamp(day_kst).date()),'market':market,
        'pre_ret_5m':float(pre.close.iloc[-1]/pre.close.iloc[-6]-1) if len(pre)>=6 else np.nan,
        'pre_ret_15m':float(pre.close.iloc[-1]/pre.close.iloc[-16]-1) if len(pre)>=16 else np.nan,
        'pre_ret_30m':plast/p0-1,
        'pre_value_5m_krw':float(v5),
        'pre_value_30m_krw':float(pre.value.sum()),
        'value5_ratio':v5/(float(base5.median())+1e-12),
        'value_accel5':v5/(float(pv5)+1e-12),
        'value30_ratio':float(pre.value.sum())/(float(base30.median())+1e-12),
        'pre_breakout_30m':plast/(pre_high+1e-12)-1,
        'post_max_60m':max_ret,
        'post_min_60m':post_low/post_open-1,
        'minutes_to_max':float((max_time-post.index[0]).total_seconds()/60.0),
    }
    for t in THRESHOLDS:
        pct=int(t*100)
        result[f'label_{pct}pct']=int(max_ret>=t)
        result[f'minutes_to_{pct}pct']=first_cross_minutes(post,post_open,t)
    return result


def score(df):
    # Transparent pre-09:00 score. Future labels are never used here.
    return (np.log1p(df.value5_ratio.clip(lower=0))*1.2+
            np.log1p(df.value30_ratio.clip(lower=0))*0.8+
            np.log1p(df.value_accel5.clip(lower=0))*1.0+
            df.pre_ret_5m.clip(-.1,.1)*8+
            df.pre_ret_15m.clip(-.15,.15)*5)


def evaluate(df,label):
    rows=[]
    for q in (.90,.95,.97,.99):
        th=df.pre_score.quantile(q); s=df[df.pre_score>=th]
        if s.empty: continue
        rows.append({'label':label,'quantile':q,'threshold':th,'signals':len(s),
                     'hit_rate_pct':s[label].mean()*100,'base_rate_pct':df[label].mean()*100,
                     'lift':s[label].mean()/(df[label].mean()+1e-12)})
    return rows


def top5_outputs(df):
    # Actual realized 09:00-10:00 movers; keep rank instead of only threshold labels.
    top5=(df.sort_values(['day_kst','post_max_60m'],ascending=[True,False])
            .groupby('day_kst',group_keys=False).head(5).copy())
    top5['rank_9am']=top5.groupby('day_kst')['post_max_60m'].rank(method='first',ascending=False).astype(int)
    top5=top5.sort_values(['day_kst','rank_9am'])
    top5.to_csv(OUT/'upbit_9am_realized_top5_daily.csv',index=False)

    repeats=(top5.groupby('market').agg(
        top5_appearances=('market','size'),
        top1_appearances=('rank_9am',lambda s:int((s==1).sum())),
        avg_rank=('rank_9am','mean'),
        avg_max_return=('post_max_60m','mean'),
        median_max_return=('post_max_60m','median'),
        avg_pre_ret_30m=('pre_ret_30m','mean'),
        avg_value5_ratio=('value5_ratio','mean'),
        avg_value30_ratio=('value30_ratio','mean'),
        avg_value_accel5=('value_accel5','mean'),
        avg_minutes_to_max=('minutes_to_max','mean')
    ).reset_index().sort_values(['top5_appearances','top1_appearances'],ascending=False))
    repeats.to_csv(OUT/'upbit_9am_top5_repeat_summary.csv',index=False)

    by_rank=(top5.groupby('rank_9am').agg(
        samples=('market','size'),
        avg_max_return=('post_max_60m','mean'),
        median_max_return=('post_max_60m','median'),
        avg_pre_ret_5m=('pre_ret_5m','mean'),
        avg_pre_ret_15m=('pre_ret_15m','mean'),
        avg_pre_ret_30m=('pre_ret_30m','mean'),
        avg_value5_ratio=('value5_ratio','mean'),
        avg_value30_ratio=('value30_ratio','mean'),
        avg_value_accel5=('value_accel5','mean'),
        avg_minutes_to_max=('minutes_to_max','mean')
    ).reset_index())
    by_rank.to_csv(OUT/'upbit_9am_top5_rank_profile.csv',index=False)
    return top5


def main():
    end=pd.Timestamp(datetime.now(timezone.utc)).floor('D')
    start=end-pd.Timedelta(days=DAYS+2)
    ms=markets(); universe=daily_value_rank(ms,start)
    print('UNIVERSE',universe,flush=True)
    rows=[]
    for ix,m in enumerate(universe,1):
        print(f'9AM {ix}/{len(universe)} {m}',flush=True)
        try: raw=candles_1m(m,start-pd.Timedelta(hours=6),end+pd.Timedelta(minutes=POST_WINDOW_MIN+1))
        except Exception as e:
            print('skip',m,e,flush=True); continue
        for day in pd.date_range(start.tz_convert('Asia/Seoul').date(),end.tz_convert('Asia/Seoul').date(),freq='D'):
            r=feature_row(m,day,raw)
            if r: rows.append(r)
    df=pd.DataFrame(rows)
    if df.empty: raise RuntimeError('no 9AM samples')
    df['pre_score']=score(df)
    df.to_csv(OUT/'upbit_9am_samples.csv',index=False)
    metrics=[]
    for lab in ['label_5pct','label_10pct','label_15pct','label_20pct']:
        metrics.extend(evaluate(df,lab))
    pd.DataFrame(metrics).to_csv(OUT/'upbit_9am_metrics.csv',index=False)

    # Predicted candidates (pre-09:00 only) and realized winners are deliberately separate.
    pred=df.sort_values(['day_kst','pre_score'],ascending=[True,False]).groupby('day_kst').head(5)
    pred.to_csv(OUT/'upbit_9am_predicted_top5_daily.csv',index=False)
    realized=top5_outputs(df)

    print(pd.DataFrame(metrics).to_string(index=False),flush=True)
    print('realized top5 rows',len(realized),flush=True)

if __name__=='__main__': main()
