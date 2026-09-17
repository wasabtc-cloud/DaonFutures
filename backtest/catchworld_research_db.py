"""Reusable CatchWorld Research DB.
Stores per-market 1m candles as gzip CSV, incrementally appends only missing recent data.
Designed for GitHub Actions cache restore/save and shared A/B research.
"""
from __future__ import annotations
import time
from pathlib import Path
import requests,pandas as pd
DB=Path('data/catchworld_research_db/1m'); DB.mkdir(parents=True,exist_ok=True)
S=requests.Session(); S.headers.update({'User-Agent':'CatchWorld-ResearchDB/1.0'}); BASE='https://api.upbit.com/v1'
def gj(url,params=None):
 for i in range(10):
  try:
   r=S.get(url,params=params,timeout=25)
   if r.status_code==429:time.sleep(min(.5*(i+1),5));continue
   r.raise_for_status();return r.json()
  except requests.RequestException:
   if i==9:raise
   time.sleep(min(.5*(i+1),5))
def markets():return sorted(x['market'] for x in gj(BASE+'/market/all') if x['market'].startswith('KRW-'))
def fetch(m,start,end):
 rows=[];to=end
 while to>start:
  x=gj(BASE+'/candles/minutes/1',{'market':m,'count':200,'to':to.strftime('%Y-%m-%dT%H:%M:%SZ')})
  if not x:break
  rows+=x;old=pd.to_datetime(x[-1]['candle_date_time_utc'],utc=True)
  if old<=start:break
  to=old-pd.Timedelta(seconds=1);time.sleep(.105)
 if not rows:return pd.DataFrame()
 d=pd.DataFrame(rows);d['time']=pd.to_datetime(d.candle_date_time_utc,utc=True)
 d=d[(d.time>=start)&(d.time<=end)].drop_duplicates('time').sort_values('time')
 return d[['time','opening_price','high_price','low_price','trade_price','candle_acc_trade_price']].rename(columns={'opening_price':'open','high_price':'high','low_price':'low','trade_price':'close','candle_acc_trade_price':'turnover'})
def load(m):
 p=DB/f'{m}.csv.gz'
 if not p.exists():return pd.DataFrame()
 d=pd.read_csv(p,parse_dates=['time']);d['time']=pd.to_datetime(d.time,utc=True);return d
def save(m,d):d.drop_duplicates('time').sort_values('time').to_csv(DB/f'{m}.csv.gz',index=False,compression='gzip')
def update(days=31):
 end=pd.Timestamp.now(tz='UTC').floor('min'); floor=end-pd.Timedelta(days=days);ms=markets()
 for i,m in enumerate(ms,1):
  old=load(m); start=floor if old.empty else max(floor,old.time.max()-pd.Timedelta(minutes=2))
  if start<end:
   try:new=fetch(m,start,end)
   except Exception as e:print('FAIL',m,type(e).__name__,flush=True);continue
   if not new.empty:old=pd.concat([old,new],ignore_index=True) if not old.empty else new
  if not old.empty:save(m,old[old.time>=floor])
  if i%10==0:print('DB_UPDATE',i,'/',len(ms),flush=True)
 print('DB_READY',len(ms),floor,end,flush=True)
if __name__=='__main__':update()
