import os
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed
import pandas as pd
import natural_prevalence_swing5 as base
import natural_prevalence_swing_compare as compare

CACHE_DIR=Path(os.environ.get('SWING_COMPARE_CACHE_DIR','.cache/swing_compare'));CACHE_DIR.mkdir(parents=True,exist_ok=True)
CHUNK_DAYS=30;CHUNK_WORKERS=6

def safe_stamp(ts):return pd.Timestamp(ts).strftime('%Y%m%dT%H%M%S')
def cache_path(prefix,market,start,end):return CACHE_DIR/f"{prefix}_{market.replace('-','_')}_{safe_stamp(start)}_{safe_stamp(end)}.pkl"
def load_cache(path):
    if path.exists():
        try:
            df=pd.read_pickle(path);print(f'CACHE HIT {path.name} rows={len(df)}',flush=True);return df
        except Exception as exc:print(f'CACHE READ FAIL {path.name}: {exc}',flush=True)
    return None

def save_cache(path,df):
    tmp=path.with_suffix(path.suffix+'.tmp');df.to_pickle(tmp);os.replace(tmp,path);print(f'CACHE SAVE {path.name} rows={len(df)}',flush=True)

ORIGINAL_MINUTE_WINDOW=base.minute_window

def cached_minute_window(market,t):
    start=t-pd.Timedelta(minutes=90);end=t+pd.Timedelta(days=1,hours=6);path=cache_path('train',market,start,end);cached=load_cache(path)
    if cached is not None:return cached
    df=ORIGINAL_MINUTE_WINDOW(market,t)
    if not df.empty:save_cache(path,df)
    return df

def fetch_chunk(market,start,end,chunk_no,total_chunks):
    rows=[];to=end+pd.Timedelta(minutes=1);pages=0
    while to>start:
        js=base.get('/candles/minutes/1',{'market':market,'count':200,'to':to.strftime('%Y-%m-%dT%H:%M:%SZ')})
        if not js:break
        rows+=js;pages+=1;old=pd.Timestamp(js[-1]['candle_date_time_utc'],tz='UTC')
        if old<=start:break
        to=old-pd.Timedelta(seconds=1)
        if pages%100==0:print(f'{market} chunk {chunk_no}/{total_chunks}: {pages} pages',flush=True)
    df=base.normalize_minutes(rows,start,end);print(f'{market} chunk {chunk_no}/{total_chunks} done rows={len(df)} pages={pages}',flush=True);return df

def cached_parallel_continuous(market,start,end):
    path=cache_path('valid',market,start,end);cached=load_cache(path)
    if cached is not None:return cached
    chunks=[];cursor=start
    while cursor<end:
        chunk_end=min(cursor+pd.Timedelta(days=CHUNK_DAYS),end);chunks.append((cursor,chunk_end));cursor=chunk_end+pd.Timedelta(minutes=1)
    print(f'{market} validation download: {len(chunks)} chunks workers={CHUNK_WORKERS}',flush=True);frames=[]
    with ThreadPoolExecutor(max_workers=CHUNK_WORKERS) as ex:
        futs=[ex.submit(fetch_chunk,market,s,e,i+1,len(chunks)) for i,(s,e) in enumerate(chunks)]
        for done,fut in enumerate(as_completed(futs),1):frames.append(fut.result());print(f'{market} progress {done}/{len(chunks)} chunks',flush=True)
    frames=[f for f in frames if f is not None and not f.empty]
    if not frames:return pd.DataFrame()
    df=pd.concat(frames).sort_index();df=df[~df.index.duplicated(keep='last')];df=df.loc[(df.index>=start)&(df.index<=end)];save_cache(path,df);return df

base.minute_window=cached_minute_window
base.fetch_continuous_minutes=cached_parallel_continuous

if __name__=='__main__':
    print('FAST SWING 5/10/20 comparison enabled: shared cached data + parallel chunks',flush=True)
    compare.main()
