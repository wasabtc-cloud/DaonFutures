import os,time,requests,pandas as pd,numpy as np
DAYS=int(os.getenv('DAYS','365')); SHARD=int(os.getenv('SHARD_INDEX','0')); SHARDS=int(os.getenv('SHARD_COUNT','8'))
FEE=.0015
S=requests.Session(); S.headers['User-Agent']='CatchWorldIndicatorResearch/1.0'

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
 d=pd.DataFrame(out).drop_duplicates('candle_date_time_utc'); d['time']=pd.to_datetime(d.candle_date_time_utc,utc=True)
 return d.sort_values('time').reset_index(drop=True)

def rsi(x,n=14):
 dx=x.diff(); up=dx.clip(lower=0).ewm(alpha=1/n,adjust=False).mean(); dn=(-dx.clip(upper=0)).ewm(alpha=1/n,adjust=False).mean()
 return 100-100/(1+up/dn.replace(0,np.nan))

def enrich(d):
 c=d.trade_price.astype(float); h=d.high_price.astype(float); l=d.low_price.astype(float); q=d.candle_acc_trade_price.astype(float)
 d['ema20']=c.ewm(span=20,adjust=False).mean(); d['ema50']=c.ewm(span=50,adjust=False).mean(); d['ema200']=c.ewm(span=200,adjust=False).mean()
 d['ema20_slope']=d.ema20/d.ema20.shift(3)-1; d['rsi14']=rsi(c)
 e12=c.ewm(span=12,adjust=False).mean(); e26=c.ewm(span=26,adjust=False).mean(); macd=e12-e26; sig=macd.ewm(span=9,adjust=False).mean(); d['macd_hist']=macd-sig
 pc=c.shift(1); tr=pd.concat([(h-l),(h-pc).abs(),(l-pc).abs()],axis=1).max(axis=1); d['atr14']=tr.ewm(alpha=1/14,adjust=False).mean(); d['atr_pct']=d.atr14/c
 d['base5']=q.rolling(72,min_periods=36).median().shift(1); d['flow']=q/d.base5; d['ret30']=c/c.shift(6)-1
 d['q_prev3_mean']=q.shift(1).rolling(3,min_periods=1).mean(); d['turnover_persist3']=d.q_prev3_mean/d.base5
 return d

def first_touch(future,entry,tp,sl):
 for _,z in future.iterrows():
  # conservative if both touched in same 5m candle: stop first
  if float(z.low_price)<=entry*(1-sl): return -sl-FEE,'SL'
  if float(z.high_price)>=entry*(1+tp): return tp-FEE,'TP'
 return float(future.trade_price.iloc[-1])/entry-1-FEE,'TIME'

def rows(m,d):
 d=enrich(d); c=d.trade_price.astype(float)
 mask=(d.flow>=6)&d.ret30.between(-.025,-.02)
 out=[]; last=None
 for i in np.flatnonzero(mask.fillna(False).to_numpy()):
  t=d.time.iloc[i]
  if last is not None and (t-last).total_seconds()<3600: continue
  if i+72>=len(d): continue
  last=t; entry=float(c.iloc[i]); fut=d.iloc[i+1:i+73]
  base=[m,t,entry,float(d.flow.iloc[i]),float(d.ret30.iloc[i]),float(d.ema20.iloc[i]),float(d.ema50.iloc[i]),float(d.ema200.iloc[i]),float(d.ema20_slope.iloc[i]),float(d.rsi14.iloc[i]),float(d.macd_hist.iloc[i]),float(d.atr_pct.iloc[i]),float(d.turnover_persist3.iloc[i])]
  vals=[]
  for sl in [.015,.02,.025,.03,.04]:
   for tp in [.03,.04,.05,.06,.08]:
    p,x=first_touch(fut,entry,tp,sl); vals += [p,x]
  out.append(base+vals)
 cols=['market','time','price','flow','ret30','ema20','ema50','ema200','ema20_slope','rsi14','macd_hist','atr_pct','turnover_persist3']
 for sl in [15,20,25,30,40]:
  for tp in [3,4,5,6,8]: cols += [f'pnl_sl{sl}_tp{tp}',f'exit_sl{sl}_tp{tp}']
 return pd.DataFrame(out,columns=cols)

parts=[]
for k,m in enumerate(markets()):
 if k%SHARDS!=SHARD: continue
 try:
  x=rows(m,candles(m));
  if len(x): parts.append(x)
 except Exception as e: print('ERR',m,e)
out=pd.concat(parts,ignore_index=True) if parts else pd.DataFrame(); out.to_csv(f'indicator_tp_sl_shard_{SHARD}.csv',index=False)
print('rows',len(out),'markets',out.market.nunique() if len(out) else 0)
