import os,time,requests,pandas as pd,numpy as np
DAYS=int(os.getenv('DAYS','365')); SHARD=int(os.getenv('SHARD_INDEX','0')); SHARDS=int(os.getenv('SHARD_COUNT','8')); FEE=.0015
S=requests.Session(); S.headers['User-Agent']='CatchWorldMarketFlowValidation/1.0'
def markets():
 r=S.get('https://api.upbit.com/v1/market/all',params={'is_details':'false'},timeout=20);r.raise_for_status();return sorted(x['market'] for x in r.json() if x['market'].startswith('KRW-'))
def candles(m):
 end=pd.Timestamp.now(tz='UTC');start=end-pd.Timedelta(days=DAYS+2);out=[];to=end
 while to>start:
  r=S.get('https://api.upbit.com/v1/candles/minutes/5',params={'market':m,'count':200,'to':to.strftime('%Y-%m-%dT%H:%M:%SZ')},timeout=20)
  if r.status_code==429:time.sleep(.35);continue
  r.raise_for_status();a=r.json()
  if not a:break
  out+=a;old=pd.to_datetime(a[-1]['candle_date_time_utc'],utc=True);to=old-pd.Timedelta(seconds=1)
  if old<=start:break
  time.sleep(.04)
 d=pd.DataFrame(out).drop_duplicates('candle_date_time_utc');d['time']=pd.to_datetime(d.candle_date_time_utc,utc=True);return d.sort_values('time').reset_index(drop=True)
def prep(d):
 q=d.candle_acc_trade_price.astype(float);c=d.trade_price.astype(float);d['base5']=q.rolling(72,min_periods=36).median().shift(1);d['flow']=q/d.base5;d['ret30']=c/c.shift(6)-1;return d
# Per-coin signal rows plus contemporaneous turnover. Merge all shards later to construct market-wide flow without look-ahead.
def collect(m,d):
 d=prep(d);q=d.candle_acc_trade_price.astype(float);c=d.trade_price.astype(float);mask=(d.flow>=6)&d.ret30.between(-.025,-.02);rows=[];last=None
 for i in np.flatnonzero(mask.fillna(False).to_numpy()):
  t=d.time.iloc[i]
  if last is not None and (t-last).total_seconds()<3600:continue
  if i+72>=len(d):continue
  last=t;e=float(c.iloc[i]);f=d.iloc[i+1:i+73];p=-.02-FEE
  for _,z in f.iterrows():
   if float(z.low_price)<=e*.98:p=-.02-FEE;break
   if float(z.high_price)>=e*1.03:p=.03-FEE;break
  else:p=float(f.trade_price.iloc[-1])/e-1-FEE
  rows.append([m,t,e,float(d.flow.iloc[i]),float(d.ret30.iloc[i]),float(q.iloc[i]),p])
 return pd.DataFrame(rows,columns=['market','time','price','flow','ret30','turnover5','pnl'])
parts=[]
for k,m in enumerate(markets()):
 if k%SHARDS!=SHARD:continue
 try:
  x=collect(m,candles(m));
  if len(x):parts.append(x)
 except Exception as e:print('ERR',m,e)
out=pd.concat(parts,ignore_index=True) if parts else pd.DataFrame();out.to_csv(f'market_flow_signal_shard_{SHARD}.csv',index=False);print('rows',len(out))
