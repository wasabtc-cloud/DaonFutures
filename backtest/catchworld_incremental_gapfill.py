"""CatchWorld incremental Upbit candle gap-fill + 09:00 KST event dataset.
Public REST only. Downloads only missing recent candles and de-duplicates by market/time.
Units: 1,5,15,60. Upbit candle API max 200/request; candle group <=10 req/s.
"""
from __future__ import annotations
import argparse,time
from pathlib import Path
import pandas as pd,requests
BASE='https://api.upbit.com/v1';KST='Asia/Seoul'
def markets():
 r=requests.get(BASE+'/market/all',params={'isDetails':'false'},timeout=20);r.raise_for_status();return sorted(x['market'] for x in r.json() if x['market'].startswith('KRW-'))
def fetch(market,unit,start,end):
 out=[];to=end.tz_convert('UTC')
 while to>start.tz_convert('UTC'):
  r=requests.get(f'{BASE}/candles/minutes/{unit}',params={'market':market,'to':to.strftime('%Y-%m-%dT%H:%M:%SZ'),'count':200},timeout=20);r.raise_for_status();z=r.json()
  if not z:break
  for x in z:
   t=pd.Timestamp(x['candle_date_time_utc'],tz='UTC')
   if t>=start.tz_convert('UTC'):out.append({'market':market,'time':t,'open':x['opening_price'],'high':x['high_price'],'low':x['low_price'],'close':x['trade_price'],'turnover':x['candle_acc_trade_price'],'volume':x['candle_acc_trade_volume']})
  oldest=pd.Timestamp(z[-1]['candle_date_time_utc'],tz='UTC');to=oldest;time.sleep(.12)
  if oldest<=start.tz_convert('UTC'):break
 return pd.DataFrame(out)
def update_unit(root,unit,lookback_days):
 p=root/f'candles_{unit}m.csv';old=pd.read_csv(p) if p.exists() else pd.DataFrame()
 if len(old):old['time']=pd.to_datetime(old.time,utc=True);start=max(old.time.max()-pd.Timedelta(hours=2),pd.Timestamp.now(tz='UTC')-pd.Timedelta(days=lookback_days))
 else:start=pd.Timestamp.now(tz='UTC')-pd.Timedelta(days=lookback_days)
 end=pd.Timestamp.now(tz='UTC')+pd.Timedelta(minutes=1);parts=[]
 for i,m in enumerate(markets(),1):
  try:parts.append(fetch(m,unit,start,end))
  except Exception as e:print('WARN',unit,m,repr(e))
  if i%25==0:print('UNIT',unit,'MARKETS',i)
 new=pd.concat(parts,ignore_index=True) if parts else pd.DataFrame()
 allx=pd.concat([old,new],ignore_index=True) if len(old) else new
 if len(allx):allx['time']=pd.to_datetime(allx.time,utc=True);allx=allx.drop_duplicates(['market','time'],keep='last').sort_values(['market','time']);allx.to_csv(p,index=False)
 print('UPDATED',unit,'ROWS',len(allx),'NEW',len(new));return allx
def event09(x):
 if not len(x):return pd.DataFrame()
 z=x.copy();z['kst']=z.time.dt.tz_convert(KST);z['day']=z.kst.dt.date;z['hour']=z.kst.dt.hour
 rows=[]
 for (m,d),g in z.groupby(['market','day']):
  g=g.sort_values('kst').set_index('kst')
  def ret(a,b):
   q=g.between_time(a,b,inclusive='both');return q.close.iloc[-1]/q.open.iloc[0]-1 if len(q) else None
  def tov(a,b):q=g.between_time(a,b,inclusive='both');return q.turnover.sum() if len(q) else None
  rows.append({'market':m,'day':d,'ret_03_06':ret('03:00','05:59'),'ret_06_08':ret('06:00','07:59'),'ret_08_09':ret('08:00','08:59'),'ret_09_10':ret('09:00','09:59'),'ret_10_12':ret('10:00','11:59'),'ret_12_15':ret('12:00','14:59'),'turn_08_09':tov('08:00','08:59'),'turn_09_10':tov('09:00','09:59')})
 return pd.DataFrame(rows)
def main():
 a=argparse.ArgumentParser();a.add_argument('--out',default='data/incremental');a.add_argument('--days',type=int,default=7);args=a.parse_args();root=Path(args.out);root.mkdir(parents=True,exist_ok=True)
 data={u:update_unit(root,u,args.days) for u in (60,15,5,1)}
 ev=event09(data[15]);ev.to_csv(root/'event_09kst_15m.csv',index=False);print('EVENT09',len(ev))
if __name__=='__main__':main()
