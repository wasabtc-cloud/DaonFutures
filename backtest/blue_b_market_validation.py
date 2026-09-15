"""Market-wide BLUE-B validation. Research only; no orders."""
import time, requests, pandas as pd, numpy as np
from pathlib import Path
OUT=Path('results_blue_b_market'); OUT.mkdir(exist_ok=True)
BASE='https://api.upbit.com/v1'

def markets():
 r=requests.get(BASE+'/market/all',params={'is_details':'false'},timeout=20); r.raise_for_status()
 return [x['market'] for x in r.json() if x['market'].startswith('KRW-')]

def candles(m, unit=15, days=90):
 need=int(days*24*60/unit)+300; out=[]; to=None
 while len(out)<need:
  p={'market':m,'count':min(200,need-len(out))}
  if to:p['to']=to
  a=requests.get(f'{BASE}/candles/minutes/{unit}',params=p,timeout=20); a.raise_for_status(); a=a.json()
  if not a:break
  out+=a; to=a[-1]['candle_date_time_utc']+'Z'; time.sleep(.12)
  if len(a)<p['count']:break
 if not out:return pd.DataFrame()
 x=pd.DataFrame(out).drop_duplicates('candle_date_time_utc').sort_values('candle_date_time_utc')
 x.index=pd.to_datetime(x.candle_date_time_utc,utc=True)
 return x

def calc(m,x):
 c=x.trade_price.astype(float); h=x.high_price.astype(float); l=x.low_price.astype(float); v=x.candle_acc_trade_price.astype(float)
 ema20=c.ewm(span=20,adjust=False).mean(); ema60=c.ewm(span=60,adjust=False).mean()
 d=c.diff(); g=d.clip(lower=0).rolling(14).mean(); q=(-d.clip(upper=0)).rolling(14).mean(); rsi=100-100/(1+g/q.replace(0,np.nan))
 mid=c.rolling(20).mean(); bbw=4*c.rolling(20).std()/mid
 # 1h value vs 30d-ish baseline on 15m bars
 v1=v.rolling(4).sum(); base=v1.shift(4).rolling(4*24*30,min_periods=4*24*5).median(); vr=v1/base
 sig=(vr>=8)&(c>=ema20)&(ema20>=ema60*.995)&(rsi>=45)&(bbw<=.05)
 # de-dupe 6h; evaluate future 6h max/min
 idx=np.flatnonzero(sig.fillna(False).to_numpy()); keep=[]; last=-999
 for i in idx:
  if i-last>=24 and i+24<len(c): keep.append(i); last=i
 rows=[]
 for i in keep:
  f=c.iloc[i+1:i+25]
  rows.append({'market':m,'time':str(x.index[i]),'vr':vr.iloc[i],'rsi':rsi.iloc[i],'bbw':bbw.iloc[i],
   'mfe6h':f.max()/c.iloc[i]-1,'mae6h':f.min()/c.iloc[i]-1,
   'hit10':int(f.max()/c.iloc[i]-1>=.10),'hit20':int(f.max()/c.iloc[i]-1>=.20)})
 return rows

rows=[]; ms=markets(); print('markets',len(ms))
for n,m in enumerate(ms,1):
 try:
  x=candles(m); rows+=calc(m,x); print(n,m,'signals',sum(r['market']==m for r in rows))
 except Exception as e: print('skip',m,e)
r=pd.DataFrame(rows); r.to_csv(OUT/'blue_b_market_signals.csv',index=False)
if len(r):
 s=pd.DataFrame([{'markets':r.market.nunique(),'signals':len(r),'hit10':r.hit10.mean(),'hit20':r.hit20.mean(),'avg_mfe6h':r.mfe6h.mean(),'median_mfe6h':r.mfe6h.median(),'avg_mae6h':r.mae6h.mean()}])
 s.to_csv(OUT/'blue_b_market_summary.csv',index=False); print(s.to_string(index=False))
else: print('no signals')
