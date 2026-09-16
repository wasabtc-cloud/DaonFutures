import os,time,requests,pandas as pd
DAYS=int(os.getenv('DAYS','365'));SHARD=int(os.getenv('SHARD_INDEX','0'));SHARDS=int(os.getenv('SHARD_COUNT','8'))
S=requests.Session();S.headers['User-Agent']='CatchWorldMarketFlowHourly/1.0'
def markets():
 r=S.get('https://api.upbit.com/v1/market/all',params={'is_details':'false'},timeout=20);r.raise_for_status();return sorted(x['market'] for x in r.json() if x['market'].startswith('KRW-'))
def one(m):
 end=pd.Timestamp.now(tz='UTC');start=end-pd.Timedelta(days=DAYS+2);to=end;out=[]
 while to>start:
  r=S.get('https://api.upbit.com/v1/candles/minutes/60',params={'market':m,'count':200,'to':to.strftime('%Y-%m-%dT%H:%M:%SZ')},timeout=20)
  if r.status_code==429:time.sleep(.35);continue
  r.raise_for_status();a=r.json()
  if not a:break
  out+=a;old=pd.to_datetime(a[-1]['candle_date_time_utc'],utc=True);to=old-pd.Timedelta(seconds=1)
  if old<=start:break
  time.sleep(.04)
 d=pd.DataFrame(out).drop_duplicates('candle_date_time_utc');d['time']=pd.to_datetime(d.candle_date_time_utc,utc=True);d['turnover1h']=d.candle_acc_trade_price.astype(float);return d[['time','turnover1h']]
parts=[]
for k,m in enumerate(markets()):
 if k%SHARDS!=SHARD:continue
 try:
  x=one(m);x['market']=m;parts.append(x)
 except Exception as e:print('ERR',m,e)
out=pd.concat(parts,ignore_index=True) if parts else pd.DataFrame();out.to_csv(f'market_flow_hourly_shard_{SHARD}.csv',index=False);print('rows',len(out),'markets',out.market.nunique() if len(out) else 0)
