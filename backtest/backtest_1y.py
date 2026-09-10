import io,zipfile,urllib.request
from datetime import date,timedelta
import pandas as pd
import numpy as np
START='2025-09-10';SYMBOLS=['BTCUSDT','ETHUSDT'];INTERVAL='15m';SL=.01;TP=.015;FEE=.0005

def rz(url):
 try:
  with urllib.request.urlopen(url,timeout=60) as r:raw=r.read()
  with zipfile.ZipFile(io.BytesIO(raw)) as z:return pd.read_csv(z.open(z.namelist()[0]),header=None)
 except Exception:return pd.DataFrame()
def get(sym):
 p=[];y,m=2025,9
 while (y,m)<=(2026,8):
  x=rz(f'https://data.binance.vision/data/futures/um/monthly/klines/{sym}/{INTERVAL}/{sym}-{INTERVAL}-{y}-{m:02d}.zip')
  if not x.empty:p.append(x)
  m+=1
  if m==13:y+=1;m=1
 d=date(2026,9,1)
 while d<date(2026,9,10):
  x=rz(f'https://data.binance.vision/data/futures/um/daily/klines/{sym}/{INTERVAL}/{sym}-{INTERVAL}-{d.isoformat()}.zip')
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
def adx(d,n=14):
 u=d.high.diff();dn=-d.low.diff();p=pd.Series(np.where((u>dn)&(u>0),u,0.),index=d.index);m=pd.Series(np.where((dn>u)&(dn>0),dn,0.),index=d.index);a=atr(d,n);pi=100*p.ewm(alpha=1/n,adjust=False).mean()/a;mi=100*m.ewm(alpha=1/n,adjust=False).mean()/a;dx=100*(pi-mi).abs()/(pi+mi).replace(0,np.nan);return dx.ewm(alpha=1/n,adjust=False).mean()
def prep(d):
 d=d.copy();d['e20']=ema(d.close,20);d['e50']=ema(d.close,50);d['rsi']=rsi(d.close);d['vma']=d.volume.rolling(20).mean();d['macd']=ema(d.close,12)-ema(d.close,26);d['macds']=ema(d['macd'],9)
 h1=d.resample('1h',label='right',closed='right').agg({'open':'first','high':'max','low':'min','close':'last','volume':'sum'}).dropna();h4=d.resample('4h',label='right',closed='right').agg({'open':'first','high':'max','low':'min','close':'last','volume':'sum'}).dropna();h1['st']=st(h1);h1['adx']=adx(h1);h4['e200']=ema(h4.close,200);h4['slope']=h4.e200-h4.e200.shift(6)
 return d.join(h1[['st','adx']].rename(columns={'st':'h1st','adx':'h1adx'})).ffill().join(h4[['e200','slope']].rename(columns={'e200':'h4e200','slope':'h4slope'})).ffill()
def base(d):
 cu=(d.close>d.e20)&(d.close.shift()<=d.e20.shift());cd=(d.close<d.e20)&(d.close.shift()>=d.e20.shift());v=d.volume>d.vma
 lo=(d.e20>d.e50)&(d.h1st==1)&cu&v&d.rsi.between(50,70)&(d.close>d.h4e200)
 sh=(d.e20<d.e50)&(d.h1st==-1)&cd&v&d.rsi.between(30,50)&(d.close<d.h4e200)
 return pd.Series(np.where(lo,1,np.where(sh,-1,0)),index=d.index)
def variants(d):
 b=base(d);L=b==1;S=b==-1
 return {
 'Baseline L+S':b,
 'LONG only':pd.Series(np.where(L,1,0),index=d.index),
 'LONG + EMA200 slope':pd.Series(np.where(L&(d.h4slope>0),1,0),index=d.index),
 'LONG + ADX20':pd.Series(np.where(L&(d.h1adx>=20),1,0),index=d.index),
 'LONG + Vol1.2x':pd.Series(np.where(L&(d.volume>d.vma*1.2),1,0),index=d.index),
 'LONG + MACD state':pd.Series(np.where(L&(d.macd>d.macds),1,0),index=d.index),
 'LONG RSI52-65':pd.Series(np.where(L&d.rsi.between(52,65),1,0),index=d.index),
 'Asym L + strict S':pd.Series(np.where(L,1,np.where(S&(d.h4slope<0)&(d.h1adx>=25),-1,0)),index=d.index)
 }
def run(d,s):
 bal=100.;peak=100.;mdd=0.;tr=[];i=0
 while i<len(d)-1:
  side=int(s.iloc[i]);
  if not side:i+=1;continue
  e=d.close.iloc[i];sl=e*(1-SL) if side==1 else e*(1+SL);tp=e*(1+TP) if side==1 else e*(1-TP);j=i+1
  while j<len(d):
   hs=d.low.iloc[j]<=sl if side==1 else d.high.iloc[j]>=sl;ht=d.high.iloc[j]>=tp if side==1 else d.low.iloc[j]<=tp
   if hs or ht:x=sl if hs else tp;o='SL' if hs else 'TP';break
   j+=1
  if j>=len(d):break
  before=bal;bal+=bal*((x/e-1)*side-2*FEE);peak=max(peak,bal);mdd=max(mdd,(peak-bal)/peak);tr.append((before,bal,o));i=j+1
 n=len(tr);w=sum(x[2]=='TP' for x in tr);gp=sum(max(0,x[1]-x[0]) for x in tr);gl=-sum(min(0,x[1]-x[0]) for x in tr)
 return bal,n,100*w/n if n else 0,gp/gl if gl else 999,100*mdd
def main():
 rows=[]
 for sym in SYMBOLS:
  print('Downloading',sym,flush=True);d=prep(get(sym));d=d.loc[d.index>=pd.Timestamp(START,tz='UTC')+pd.Timedelta(days=35)]
  cut=d.index[int(len(d)*0.5)]
  for name,s in variants(d).items():
   for period,dd,ss in [('FULL',d,s),('H2',d.loc[cut:],s.loc[cut:])]:
    b,n,w,p,m=run(dd,ss);rows.append([sym,name,period,round(b,2),round(b-100,2),n,round(w,2),round(p,2),round(m,2)])
 out=pd.DataFrame(rows,columns=['Symbol','Strategy','Period','Final_USDT','Return_pct','Trades','WinRate_pct','ProfitFactor','MaxDD_pct']);print(out.to_string(index=False));out.to_csv('backtest_results.csv',index=False)
if __name__=='__main__':main()
