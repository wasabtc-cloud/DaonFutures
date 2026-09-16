import os,time,requests,pandas as pd,numpy as np
DAYS=int(os.getenv('DAYS','365')); SHARD=int(os.getenv('SHARD_INDEX','0')); SHARDS=int(os.getenv('SHARD_COUNT','8'))
S=requests.Session(); S.headers['User-Agent']='CatchWorldResearch/1.1'

def markets():
 r=S.get('https://api.upbit.com/v1/market/all',params={'is_details':'false'},timeout=20); r.raise_for_status()
 return sorted(x['market'] for x in r.json() if x['market'].startswith('KRW-'))

def candles(m):
 end=pd.Timestamp.now(tz='UTC'); start=end-pd.Timedelta(days=DAYS+2); out=[]; to=end
 while to>start:
  r=S.get('https://api.upbit.com/v1/candles/minutes/5',params={'market':m,'count':200,'to':to.strftime('%Y-%m-%dT%H:%M:%SZ')},timeout=20)
  if r.status_code==429: time.sleep(.35); continue
  r.raise_for_status(); a=r.json()
  if not a: break
  out.extend(a); oldest=pd.to_datetime(a[-1]['candle_date_time_utc'],utc=True); to=oldest-pd.Timedelta(seconds=1)
  if oldest<=start: break
  time.sleep(.04)
 d=pd.DataFrame(out).drop_duplicates('candle_date_time_utc')
 d['time']=pd.to_datetime(d.candle_date_time_utc,utc=True); d=d.sort_values('time')
 return d[d.time>=end-pd.Timedelta(days=DAYS)].reset_index(drop=True)

def research_rows(m,d):
 if len(d)<150:return pd.DataFrame()
 q=d.candle_acc_trade_price.astype(float); c=d.trade_price.astype(float); hi=d.high_price.astype(float); lo=d.low_price.astype(float)
 base5=q.rolling(72,min_periods=36).median().shift(1)
 flow=q/base5
 excess=q-base5
 ret30=c/c.shift(6)-1
 turnover24=q.rolling(288,min_periods=144).sum().shift(1)
 # Store a broad research universe, not only the locked 8x signal, so thresholds can be retested without redownloading.
 mask=(flow>=2.0)&ret30.between(-.05,.03)
 rows=[]
 for i in np.flatnonzero(mask.fillna(False).to_numpy()):
  if i+72>=len(d):continue
  entry=c.iloc[i]; future=d.iloc[i+1:i+73]
  if future.empty:continue
  mfe=float(future.high_price.astype(float).max()/entry-1); mae=float(future.low_price.astype(float).min()/entry-1)
  pnl=None
  for _,z in future.iterrows():
   if float(z.low_price)<=entry*.98: pnl=-.0215; break
   if float(z.high_price)>=entry*1.03: pnl=.0285; break
  if pnl is None:pnl=float(future.trade_price.iloc[-1])/entry-1-.0015
  rows.append([m,d.time.iloc[i],entry,q.iloc[i],base5.iloc[i],excess.iloc[i],flow.iloc[i],turnover24.iloc[i],ret30.iloc[i],mfe,mae,pnl])
 return pd.DataFrame(rows,columns=['market','time','price','turnover_5m','baseline_5m_median_6h','excess_turnover_5m','flow','turnover_24h','ret30','mfe_6h','mae_6h','pnl_tp3_sl2_6h'])

parts=[]
for k,m in enumerate(markets()):
 if k%SHARDS!=SHARD:continue
 try:
  x=research_rows(m,candles(m))
  if len(x):parts.append(x)
 except Exception as e:print('ERR',m,e)
out=pd.concat(parts,ignore_index=True) if parts else pd.DataFrame()
out.to_csv(f'turnover_research_shard_{SHARD}.csv',index=False)
print('rows',len(out),'markets',out.market.nunique() if len(out) else 0)
