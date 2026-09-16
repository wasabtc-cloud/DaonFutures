import os,time,requests,pandas as pd,numpy as np
DAYS=int(os.getenv('DAYS','365')); SHARD=int(os.getenv('SHARD_INDEX','0')); SHARDS=int(os.getenv('SHARD_COUNT','8'))
S=requests.Session(); S.headers['User-Agent']='CatchWorldStrategyB/1.0'
def markets():
 r=S.get('https://api.upbit.com/v1/market/all',params={'is_details':'false'},timeout=20); r.raise_for_status(); return sorted(x['market'] for x in r.json() if x['market'].startswith('KRW-'))
def candles(m):
 end=pd.Timestamp.now(tz='UTC'); start=end-pd.Timedelta(days=DAYS+35); to=end; out=[]
 while to>start:
  r=S.get('https://api.upbit.com/v1/candles/minutes/60',params={'market':m,'count':200,'to':to.strftime('%Y-%m-%dT%H:%M:%SZ')},timeout=20)
  if r.status_code==429: time.sleep(.5); continue
  r.raise_for_status(); a=r.json()
  if not a: break
  out+=a; old=pd.to_datetime(a[-1]['candle_date_time_utc'],utc=True); to=old-pd.Timedelta(seconds=1)
  if old<=start: break
  time.sleep(.045)
 d=pd.DataFrame(out).drop_duplicates('candle_date_time_utc').sort_values('candle_date_time_utc')
 d['time']=pd.to_datetime(d.candle_date_time_utc,utc=True); d=d[d.time>=end-pd.Timedelta(days=DAYS+30)].copy()
 d['open']=d.opening_price.astype(float); d['high']=d.high_price.astype(float); d['low']=d.low_price.astype(float); d['close']=d.trade_price.astype(float); d['turnover']=d.candle_acc_trade_price.astype(float); d['volume']=d.candle_acc_trade_volume.astype(float)
 return d.reset_index(drop=True)
def build(m):
 d=candles(m); c=d.close; tv=d.turnover
 # All features are trailing/causal at timestamp t.
 for h in [6,12,24,72,168,336,720]:
  d[f'ret_{h}h']=c/c.shift(h)-1
  d[f'turn_{h}h']=tv.rolling(h,min_periods=max(3,h//2)).sum()
 d['turn_base7d']=tv.rolling(168,min_periods=72).median().shift(1)
 d['turn_ratio']=tv/d.turn_base7d
 d['turn_accel_6_24']=d.turn_6h/(d.turn_24h/4).replace(0,np.nan)
 d['range24']=(d.high.rolling(24).max()/d.low.rolling(24).min()-1)
 d['range72']=(d.high.rolling(72).max()/d.low.rolling(72).min()-1)
 d['drawdown_30d']=c/d.high.rolling(720,min_periods=168).max()-1
 # Forward labels only; never used as features.
 fut=[]
 arr=c.to_numpy(float)
 for i,p in enumerate(arr):
  z={}
  for h in [6,12,24,48,72]:
   q=arr[i+1:min(len(arr),i+h+1)]
   z[f'fwd_mfe_{h}h']=float(np.max(q/p-1)) if len(q) else np.nan
  fut.append(z)
 for k in fut[0]: d[k]=[x[k] for x in fut]
 d['market']=m
 keep=['market','time','close','turnover','turn_ratio','turn_accel_6_24','range24','range72','drawdown_30d']+[f'ret_{h}h' for h in [6,12,24,72,168,336,720]]+[f'fwd_mfe_{h}h' for h in [6,12,24,48,72]]
 return d[keep]
parts=[]
for k,m in enumerate(markets()):
 if k%SHARDS!=SHARD: continue
 try: parts.append(build(m)); print('OK',m)
 except Exception as e: print('ERR',m,e)
out=pd.concat(parts,ignore_index=True) if parts else pd.DataFrame()
out.to_csv(f'strategy_b_scout_shard_{SHARD}.csv',index=False)
# Event summary: large forward movers and their PRE-move causal features.
if len(out):
 e=out[out.fwd_mfe_24h>=.20].copy(); e.to_csv(f'strategy_b_events_shard_{SHARD}.csv',index=False)
 print('ROWS',len(out),'EVENT_ROWS_20PCT_24H',len(e),'MARKETS',out.market.nunique())
else: print('ROWS 0')
