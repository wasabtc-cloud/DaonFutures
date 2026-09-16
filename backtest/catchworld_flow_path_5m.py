import os,time,requests,pandas as pd,numpy as np
DAYS=int(os.getenv('DAYS','365'));SHARD=int(os.getenv('SHARD_INDEX','0'));SHARDS=int(os.getenv('SHARD_COUNT','8'))
S=requests.Session();S.headers['User-Agent']='CatchWorldFlowPath/1.0'
def markets():
 r=S.get('https://api.upbit.com/v1/market/all',params={'is_details':'false'},timeout=20);r.raise_for_status();return sorted(x['market'] for x in r.json() if x['market'].startswith('KRW-'))
def candles(m):
 end=pd.Timestamp.now(tz='UTC');start=end-pd.Timedelta(days=DAYS+2);to=end;out=[]
 while to>start:
  r=S.get('https://api.upbit.com/v1/candles/minutes/5',params={'market':m,'count':200,'to':to.strftime('%Y-%m-%dT%H:%M:%SZ')},timeout=20)
  if r.status_code==429: time.sleep(.4);continue
  r.raise_for_status();a=r.json()
  if not a:break
  out+=a;old=pd.to_datetime(a[-1]['candle_date_time_utc'],utc=True);to=old-pd.Timedelta(seconds=1)
  if old<=start:break
  time.sleep(.045)
 d=pd.DataFrame(out).drop_duplicates('candle_date_time_utc').sort_values('candle_date_time_utc')
 d['time']=pd.to_datetime(d.candle_date_time_utc,utc=True);d=d[d.time>=end-pd.Timedelta(days=DAYS)]
 d['price']=d.trade_price.astype(float);d['turnover5']=d.candle_acc_trade_price.astype(float)
 d['base72']=d.turnover5.rolling(72,min_periods=36).median().shift(1);d['flow']=d.turnover5/d.base72
 d['ret30']=d.price/d.price.shift(6)-1
 return d[['time','price','turnover5','base72','flow','ret30']].reset_index(drop=True)
def process(m):
 d=candles(m);mask=(d.flow>=6)&d.ret30.between(-.025,-.020);idx=np.flatnonzero(mask);rows=[];last=None
 for i in idx:
  t=d.time.iloc[i]
  if last is not None and (t-last).total_seconds()<3600:continue
  last=t
  # Store 60m before through 6h after, 5m resolution, relative to candidate entry.
  for j in range(max(0,i-12),min(len(d),i+73)):
   r=d.iloc[j];rows.append((m,t,r.time,(j-i)*5,r.price,r.turnover5,r.base72,r.flow,r.ret30))
 return rows
rows=[]
for k,m in enumerate(markets()):
 if k%SHARDS!=SHARD:continue
 try: rows+=process(m)
 except Exception as e: print('ERR',m,e)
out=pd.DataFrame(rows,columns=['market','entry_time','time','offset_min','price','turnover5','base72','flow','ret30'])
out.to_csv(f'flow_path_5m_shard_{SHARD}.csv',index=False);print('rows',len(out),'events',out[['market','entry_time']].drop_duplicates().shape[0] if len(out) else 0)
