import os,time,requests,pandas as pd,numpy as np
DAYS=int(os.getenv('DAYS','365')); SHARD=int(os.getenv('SHARD_INDEX','0')); SHARDS=int(os.getenv('SHARD_COUNT','4')); FEE=.0015
FLOW_MIN=8.; PB_LO=-.03; PB_HI=-.015; COOLDOWN=pd.Timedelta(minutes=60)
S=requests.Session(); S.headers['User-Agent']='CatchWorldResearch/1.0'
def markets():
 r=S.get('https://api.upbit.com/v1/market/all',params={'is_details':'false'},timeout=20);r.raise_for_status();return sorted(x['market'] for x in r.json() if x['market'].startswith('KRW-'))
def candles(m):
 end=pd.Timestamp.now(tz='UTC'); start=end-pd.Timedelta(days=DAYS+2); out=[]; to=end
 while to>start:
  r=S.get('https://api.upbit.com/v1/candles/minutes/5',params={'market':m,'count':200,'to':to.strftime('%Y-%m-%dT%H:%M:%SZ')},timeout=20)
  if r.status_code==429: time.sleep(.3); continue
  r.raise_for_status(); a=r.json()
  if not a: break
  out.extend(a); oldest=pd.to_datetime(a[-1]['candle_date_time_utc'],utc=True); to=oldest-pd.Timedelta(seconds=1)
  if oldest<=start: break
  time.sleep(.035)
 d=pd.DataFrame(out).drop_duplicates('candle_date_time_utc'); d['time']=pd.to_datetime(d.candle_date_time_utc,utc=True); d=d.sort_values('time'); return d[d.time>=end-pd.Timedelta(days=DAYS)]
def run(m,d):
 if len(d)<150:return []
 q=d.candle_acc_trade_price.astype(float); c=d.trade_price.astype(float); hi=d.high_price.astype(float); lo=d.low_price.astype(float)
 base=q.rolling(72,min_periods=36).median().shift(1); flow=q/base; ret30=c/c.shift(6)-1
 cand=(flow>=FLOW_MIN)&(ret30>=PB_LO)&(ret30<=PB_HI); rows=[]; last=None
 for i in np.flatnonzero(cand.to_numpy()):
  if i+72>=len(d):continue
  t=d.time.iloc[i]
  if last is not None and t-last<COOLDOWN:continue
  last=t; entry=c.iloc[i]; pnl=None; exit_t=None
  for j in range(i+1,min(i+73,len(d))):
   tp=hi.iloc[j]>=entry*1.03; sl=lo.iloc[j]<=entry*.98
   if sl: pnl=-.02-FEE; exit_t=d.time.iloc[j]; break
   if tp: pnl=.03-FEE; exit_t=d.time.iloc[j]; break
  if pnl is None:
   j=min(i+72,len(d)-1); pnl=c.iloc[j]/entry-1-FEE; exit_t=d.time.iloc[j]
  rows.append([m,t,flow.iloc[i],ret30.iloc[i],exit_t,pnl])
 return rows
allrows=[]
for k,m in enumerate(markets()):
 if k%SHARDS!=SHARD:continue
 try: allrows+=run(m,candles(m))
 except Exception as e: print('ERR',m,e)
pd.DataFrame(allrows,columns=['market','entry_time','flow','ret30','exit_time','pnl']).to_csv(f'locked_long_shard_{SHARD}.csv',index=False)
print('rows',len(allrows))
