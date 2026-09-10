import io,zipfile,urllib.request
from datetime import date,timedelta
import pandas as pd
import numpy as np
START='2025-09-10';SYMBOLS=['BTCUSDT','ETHUSDT'];INTERVAL='5m';SL_PCT=.01;TP_PCT=.015;FEE_RATE=.0005

def rz(url):
 try:
  with urllib.request.urlopen(url,timeout=60) as r:raw=r.read()
  with zipfile.ZipFile(io.BytesIO(raw)) as z:return pd.read_csv(z.open(z.namelist()[0]),header=None)
 except Exception as e:print('skip',url,e);return pd.DataFrame()
def get(symbol):
 p=[];y,m=2025,9
 while (y,m)<=(2026,8):
  x=rz(f'https://data.binance.vision/data/futures/um/monthly/klines/{symbol}/{INTERVAL}/{symbol}-{INTERVAL}-{y}-{m:02d}.zip')
  if not x.empty:p.append(x)
  m+=1
  if m==13:y+=1;m=1
 d=date(2026,9,1)
 while d<date(2026,9,10):
  x=rz(f'https://data.binance.vision/data/futures/um/daily/klines/{symbol}/{INTERVAL}/{symbol}-{INTERVAL}-{d.isoformat()}.zip')
  if not x.empty:p.append(x)
  d+=timedelta(days=1)
 r=pd.concat(p).iloc[:,:12];r.columns=['time','open','high','low','close','volume','ct','qv','tr','tb','tq','ig']
 for c in ['time','open','high','low','close','volume']:r[c]=pd.to_numeric(r[c],errors='coerce')
 r=r.dropna(subset=['time','open','high','low','close','volume']);r['time']=pd.to_datetime(r.time.astype('int64'),unit='ms',utc=True)
 return r.drop_duplicates('time').set_index('time').sort_index()[['open','high','low','close','volume']]
def ema(s,n):return s.ewm(span=n,adjust=False).mean()
def rsi(s,n=14):
 x=s.diff();u=x.clip(lower=0).ewm(alpha=1/n,adjust=False).mean();v=(-x.clip(upper=0)).ewm(alpha=1/n,adjust=False).mean();return (100-100/(1+u/v.replace(0,np.nan))).fillna(100)
def atr(d,n=14):
 pc=d.close.shift();tr=pd.concat([d.high-d.low,(d.high-pc).abs(),(d.low-pc).abs()],axis=1).max(axis=1);return tr.ewm(alpha=1/n,adjust=False).mean()
def st(d,n=10,k=3):
 a=atr(d,n);hl=(d.high+d.low)/2;ub=hl+k*a;lb=hl-k*a;fu=ub.copy();fl=lb.copy();t=pd.Series(1,index=d.index,dtype=int)
 for i in range(1,len(d)):
  fu.iloc[i]=ub.iloc[i] if ub.iloc[i]<fu.iloc[i-1] or d.close.iloc[i-1]>fu.iloc[i-1] else fu.iloc[i-1]
  fl.iloc[i]=lb.iloc[i] if lb.iloc[i]>fl.iloc[i-1] or d.close.iloc[i-1]<fl.iloc[i-1] else fl.iloc[i-1]
  t.iloc[i]=1 if d.close.iloc[i]>fu.iloc[i-1] else (-1 if d.close.iloc[i]<fl.iloc[i-1] else t.iloc[i-1])
 return t
def prep(d):
 d=d.copy();d['e20']=ema(d.close,20);d['e50']=ema(d.close,50);d['rsi']=rsi(d.close);d['vma']=d.volume.rolling(20).mean()
 h1=d.resample('1h',label='right',closed='right').agg({'open':'first','high':'max','low':'min','close':'last','volume':'sum'}).dropna();h4=d.resample('4h',label='right',closed='right').agg({'open':'first','high':'max','low':'min','close':'last','volume':'sum'}).dropna();h1['st']=st(h1);h4['e200']=ema(h4.close,200)
 return d.join(h1[['st']].rename(columns={'st':'h1st'})).ffill().join(h4[['e200']].rename(columns={'e200':'h4e200'})).ffill()
def supertrend(d):
 cu=(d.close>d.e20)&(d.close.shift()<=d.e20.shift());cd=(d.close<d.e20)&(d.close.shift()>=d.e20.shift());v=d.volume>d.vma
 lo=(d.e20>d.e50)&(d.close>d.h4e200)&(d.h1st==1)&cu&v&d.rsi.between(50,70)
 sh=(d.e20<d.e50)&(d.close<d.h4e200)&(d.h1st==-1)&cd&v&d.rsi.between(30,50)
 return pd.Series(np.where(lo,1,np.where(sh,-1,0)),index=d.index)
def run(d,s):
 bal=100.;peak=100.;mdd=0.;tr=[];i=0
 while i<len(d)-1:
  side=int(s.iloc[i])
  if not side:i+=1;continue
  e=d.close.iloc[i];sl=e*(1-SL_PCT) if side==1 else e*(1+SL_PCT);tp=e*(1+TP_PCT) if side==1 else e*(1-TP_PCT);j=i+1
  while j<len(d):
   hs=d.low.iloc[j]<=sl if side==1 else d.high.iloc[j]>=sl;ht=d.high.iloc[j]>=tp if side==1 else d.low.iloc[j]<=tp
   if hs or ht:x=sl if hs else tp;o='SL' if hs else 'TP';break
   j+=1
  if j>=len(d):break
  before=bal;bal+=bal*((x/e-1)*side-2*FEE_RATE);peak=max(peak,bal);mdd=max(mdd,(peak-bal)/peak);tr.append((before,bal,o,side));i=j+1
 n=len(tr);w=sum(x[2]=='TP' for x in tr);gp=sum(max(0,x[1]-x[0]) for x in tr);gl=-sum(min(0,x[1]-x[0]) for x in tr)
 return bal,n,100*w/n if n else 0,gp/gl if gl else 999,100*mdd

def main():
 rows=[]
 for sym in SYMBOLS:
  print('Downloading',sym,flush=True);d=prep(get(sym));d=d.loc[d.index>=pd.Timestamp(START,tz='UTC')+pd.Timedelta(days=35)];base=supertrend(d)
  for name,s in [('LONG only',base.where(base==1,0)),('SHORT only',base.where(base==-1,0)),('LONG + SHORT',base)]:
   b,n,w,p,m=run(d,s);rows.append([sym,name,round(b,2),round(b-100,2),n,round(w,2),round(p,2),round(m,2)])
 out=pd.DataFrame(rows,columns=['Symbol','Mode','Final_USDT','Return_pct','Trades','WinRate_pct','ProfitFactor','MaxDD_pct']);print(out.to_string(index=False));out.to_csv('backtest_results.csv',index=False)
if __name__=='__main__':main()
