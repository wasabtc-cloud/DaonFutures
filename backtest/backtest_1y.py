import math, io, zipfile, urllib.request
from datetime import date, timedelta
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
START='2025-09-10'; END='2026-09-10'; SYMBOLS=['BTCUSDT','ETHUSDT']; START_BAL=100.; SL_PCT=.01; TP_PCT=.015; FEE_RATE=.0005

def read_zip_csv(url):
 try:
  with urllib.request.urlopen(url,timeout=60) as r: raw=r.read()
  with zipfile.ZipFile(io.BytesIO(raw)) as z:
   with z.open(z.namelist()[0]) as f:return pd.read_csv(f,header=None)
 except Exception as e: print('skip',url,e,flush=True); return pd.DataFrame()
def get_klines(symbol,interval='15m'):
 parts=[]; y,m=2025,9
 while (y,m)<=(2026,8):
  x=read_zip_csv(f'https://data.binance.vision/data/futures/um/monthly/klines/{symbol}/{interval}/{symbol}-{interval}-{y}-{m:02d}.zip')
  if not x.empty:parts.append(x)
  m+=1
  if m==13:y+=1;m=1
 d=date(2026,9,1)
 while d<date(2026,9,10):
  ds=d.isoformat();x=read_zip_csv(f'https://data.binance.vision/data/futures/um/daily/klines/{symbol}/{interval}/{symbol}-{interval}-{ds}.zip')
  if not x.empty:parts.append(x)
  d+=timedelta(days=1)
 raw=pd.concat(parts,ignore_index=True).iloc[:,:12];raw.columns=['open_time','open','high','low','close','volume','close_time','qv','trades','tb','tq','ignore']
 for c in ['open','high','low','close','volume']:raw[c]=pd.to_numeric(raw[c],errors='coerce')
 raw['open_time']=pd.to_numeric(raw.open_time,errors='coerce');raw=raw.dropna();raw['open_time']=pd.to_datetime(raw.open_time.astype('int64'),unit='ms',utc=True);raw=raw.drop_duplicates('open_time').set_index('open_time').sort_index();return raw.loc[(raw.index>=pd.Timestamp(START,tz='UTC'))&(raw.index<pd.Timestamp(END,tz='UTC')),['open','high','low','close','volume']]
def ema(s,n):return s.ewm(span=n,adjust=False).mean()
def rsi(s,n=14):
 d=s.diff();up=d.clip(lower=0);dn=-d.clip(upper=0);ag=up.ewm(alpha=1/n,adjust=False).mean();al=dn.ewm(alpha=1/n,adjust=False).mean();return (100-100/(1+ag/al.replace(0,np.nan))).fillna(100)
def atr(d,n=14):
 pc=d.close.shift(1);tr=pd.concat([d.high-d.low,(d.high-pc).abs(),(d.low-pc).abs()],axis=1).max(axis=1);return tr.ewm(alpha=1/n,adjust=False).mean()
def supertrend(d,n=10,mult=3.):
 a=atr(d,n);hl=(d.high+d.low)/2;ub=hl+mult*a;lb=hl-mult*a;fu=ub.copy();fl=lb.copy();t=pd.Series(1,index=d.index,dtype=int)
 for i in range(1,len(d)):
  fu.iloc[i]=ub.iloc[i] if ub.iloc[i]<fu.iloc[i-1] or d.close.iloc[i-1]>fu.iloc[i-1] else fu.iloc[i-1];fl.iloc[i]=lb.iloc[i] if lb.iloc[i]>fl.iloc[i-1] or d.close.iloc[i-1]<fl.iloc[i-1] else fl.iloc[i-1]
  t.iloc[i]=1 if d.close.iloc[i]>fu.iloc[i-1] else (-1 if d.close.iloc[i]<fl.iloc[i-1] else t.iloc[i-1])
 return t
def prep(d):
 d=d.copy();d['ema20']=ema(d.close,20);d['ema50']=ema(d.close,50);d['rsi']=rsi(d.close);d['vma20']=d.volume.rolling(20).mean();h1=d.resample('1h',label='right',closed='right').agg({'open':'first','high':'max','low':'min','close':'last','volume':'sum'}).dropna();h4=d.resample('4h',label='right',closed='right').agg({'open':'first','high':'max','low':'min','close':'last','volume':'sum'}).dropna();h1['ema20']=ema(h1.close,20);h1['ema50']=ema(h1.close,50);h1['st']=supertrend(h1);h4['ema20']=ema(h4.close,20);h4['ema50']=ema(h4.close,50);h4['ema200']=ema(h4.close,200)
 d=d.join(h1[['ema20','ema50','st']].rename(columns={'ema20':'h1e20','ema50':'h1e50','st':'h1st'}),how='left').ffill();d=d.join(h4[['ema20','ema50','ema200']].rename(columns={'ema20':'h4e20','ema50':'h4e50','ema200':'h4e200'}),how='left').ffill();return d
def current(d):
 pe=d.ema20.shift(1);lo=(d.low.shift(1)<=pe)&(d.close>d.ema20);sh=(d.high.shift(1)>=pe)&(d.close<d.ema20);return pd.Series(np.where((d.h4e20>d.h4e50)&(d.h1e20>d.h1e50)&lo&(d.rsi>=50),1,np.where((d.h4e20<d.h4e50)&(d.h1e20<d.h1e50)&sh&(d.rsi<=50),-1,0)),index=d.index)
def recommended(d):
 cu=(d.close>d.ema20)&(d.close.shift(1)<=d.ema20.shift(1));cd=(d.close<d.ema20)&(d.close.shift(1)>=d.ema20.shift(1));v=d.volume>d.vma20;lo=(d.ema20>d.ema50)&(d.close>d.h4e200)&(d.h1st==1)&cu&v&(d.rsi.between(50,70));sh=(d.ema20<d.ema50)&(d.close<d.h4e200)&(d.h1st==-1)&cd&v&(d.rsi.between(30,50));return pd.Series(np.where(lo,1,np.where(sh,-1,0)),index=d.index)
def bos_fvg(d):
 swing_hi=d.high.shift(1).rolling(20).max();swing_lo=d.low.shift(1).rolling(20).min();bos_up=d.close>swing_hi;bos_dn=d.close<swing_lo
 bull_fvg=d.low>d.high.shift(2);bear_fvg=d.high<d.low.shift(2)
 bull_low=d.high.shift(2);bull_high=d.low;bear_low=d.high;bear_high=d.low.shift(2)
 sig=np.zeros(len(d),dtype=int);pending=None;expiry=-1
 for i in range(2,len(d)):
  if bos_up.iloc[i] and bull_fvg.iloc[i] and d.close.iloc[i]>d.h4e200.iloc[i]: pending=('L',bull_low.iloc[i],bull_high.iloc[i]);expiry=i+12
  elif bos_dn.iloc[i] and bear_fvg.iloc[i] and d.close.iloc[i]<d.h4e200.iloc[i]: pending=('S',bear_low.iloc[i],bear_high.iloc[i]);expiry=i+12
  if pending is not None and i<=expiry:
   side,lo,hi=pending
   touched=(d.low.iloc[i]<=hi and d.high.iloc[i]>=lo)
   if touched:
    if side=='L' and d.close.iloc[i]>lo: sig[i]=1;pending=None
    elif side=='S' and d.close.iloc[i]<hi: sig[i]=-1;pending=None
  elif i>expiry: pending=None
 return pd.Series(sig,index=d.index)
def run(d,s):
 bal=100.;peak=bal;mdd=0.;ts=[];eq=[(d.index[0],bal)];i=0
 while i<len(d)-1:
  side=int(s.iloc[i])
  if side==0:i+=1;continue
  e=d.close.iloc[i];sl=e*(1-SL_PCT) if side==1 else e*(1+SL_PCT);tp=e*(1+TP_PCT) if side==1 else e*(1-TP_PCT);j=i+1;o=None
  while j<len(d):
   hs=d.low.iloc[j]<=sl if side==1 else d.high.iloc[j]>=sl;ht=d.high.iloc[j]>=tp if side==1 else d.low.iloc[j]<=tp
   if hs:o='SL';x=sl;break
   if ht:o='TP';x=tp;break
   j+=1
  if o is None:break
  before=bal;bal+=bal*((x/e-1)*side-2*FEE_RATE);peak=max(peak,bal);mdd=max(mdd,(peak-bal)/peak);ts.append((before,bal,o));eq.append((d.index[j],bal));i=j+1
 n=len(ts);w=sum(t[2]=='TP' for t in ts);gp=sum(max(0,t[1]-t[0]) for t in ts);gl=-sum(min(0,t[1]-t[0]) for t in ts);return {'final':bal,'ret':bal-100,'n':n,'wr':100*w/n if n else 0,'pf':gp/gl if gl else 999,'mdd':100*mdd,'eq':eq}
def main():
 rows=[];fig,axes=plt.subplots(2,1,figsize=(12,12));strategies=[('Current app',current),('Supertrend filter',recommended),('BOS FVG',bos_fvg)]
 for ax,sym in zip(axes,SYMBOLS):
  print('Downloading',sym,flush=True);d=prep(get_klines(sym));d=d.loc[d.index>=pd.Timestamp(START,tz='UTC')+pd.Timedelta(days=35)]
  for name,fn in strategies:
   b=run(d,fn(d));rows.append({'Symbol':sym,'Strategy':name,'Final_USDT':round(b['final'],2),'Return_pct':round(b['ret'],2),'Trades':b['n'],'WinRate_pct':round(b['wr'],2),'ProfitFactor':round(b['pf'],2),'MaxDD_pct':round(b['mdd'],2)});ax.plot([x for x,y in b['eq']],[y for x,y in b['eq']],label=f'{name} ${b["final"]:.2f} WR {b["wr"]:.1f}%')
  ax.axhline(100,ls='--',lw=1);ax.set_title(sym+' 1Y');ax.grid(alpha=.2);ax.legend()
 plt.tight_layout();plt.savefig('backtest_equity.png',dpi=180);pd.DataFrame(rows).to_csv('backtest_results.csv',index=False);print(pd.DataFrame(rows).to_string(index=False))
if __name__=='__main__':main()
