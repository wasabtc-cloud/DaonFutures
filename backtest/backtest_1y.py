import io,zipfile,urllib.request
from datetime import date,timedelta
import pandas as pd
import numpy as np

SYMBOL='ETHUSDT'; INTERVAL='15m'; FEE=.0005
START=pd.Timestamp('2023-09-10',tz='UTC'); END=pd.Timestamp('2026-09-10',tz='UTC')
SL=.010; TP=.020; LEV=3

def rz(url):
 try:
  with urllib.request.urlopen(url,timeout=60) as r: raw=r.read()
  with zipfile.ZipFile(io.BytesIO(raw)) as z: return pd.read_csv(z.open(z.namelist()[0]),header=None)
 except Exception as e:
  print('skip',url,e,flush=True); return pd.DataFrame()

def get(sym):
 p=[]; y,m=2023,8
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
 for c in ['time','open','high','low','close','volume']: r[c]=pd.to_numeric(r[c],errors='coerce')
 r=r.dropna(subset=['time','open','high','low','close','volume']);r['time']=pd.to_datetime(r.time.astype('int64'),unit='ms',utc=True)
 return r.drop_duplicates('time').set_index('time').sort_index()[['open','high','low','close','volume']]

def ema(s,n): return s.ewm(span=n,adjust=False).mean()
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
 d=d.copy();d['e20']=ema(d.close,20);d['e50']=ema(d.close,50);d['rsi']=rsi(d.close);d['vma']=d.volume.rolling(20).mean()
 h1=d.resample('1h',label='right',closed='right').agg({'open':'first','high':'max','low':'min','close':'last','volume':'sum'}).dropna();h4=d.resample('4h',label='right',closed='right').agg({'open':'first','high':'max','low':'min','close':'last','volume':'sum'}).dropna()
 h1['st']=st(h1);h1['adx']=adx(h1);h4['e200']=ema(h4.close,200);h4['slope']=h4.e200-h4.e200.shift(6)
 return d.join(h1[['st','adx']].rename(columns={'st':'h1st','adx':'h1adx'})).ffill().join(h4[['e200','slope']].rename(columns={'e200':'h4e200','slope':'h4slope'})).ffill()
def signal(d):
 cu=(d.close>d.e20)&(d.close.shift()<=d.e20.shift());cd=(d.close<d.e20)&(d.close.shift()>=d.e20.shift());v=d.volume>d.vma
 L=(d.e20>d.e50)&(d.h1st==1)&cu&v&d.rsi.between(50,70)&(d.close>d.h4e200)
 S=(d.e20<d.e50)&(d.h1st==-1)&cd&v&d.rsi.between(30,50)&(d.close<d.h4e200)
 return pd.Series(np.where(L,1,np.where(S&(d.h4slope<0)&(d.h1adx>=25),-1,0)),index=d.index)
def run(d,s,start_balance=100.):
 bal=start_balance;peak=bal;mdd=0.;n=w=0;i=0;longs=shorts=0
 while i<len(d)-1 and bal>1:
  side=int(s.iloc[i])
  if side==0:i+=1;continue
  longs+=side==1;shorts+=side==-1;e=d.close.iloc[i];stop=e*(1-SL) if side==1 else e*(1+SL);take=e*(1+TP) if side==1 else e*(1-TP);j=i+1
  while j<len(d):
   hs=d.low.iloc[j]<=stop if side==1 else d.high.iloc[j]>=stop;ht=d.high.iloc[j]>=take if side==1 else d.low.iloc[j]<=take
   if hs or ht:x=stop if hs else take;win=not hs;break
   j+=1
  if j>=len(d):break
  r=((x/e-1)*side-2*FEE)*LEV;bal*=max(0,1+r);peak=max(peak,bal);mdd=max(mdd,(peak-bal)/peak);n+=1;w+=int(win);i=j+1
 return [bal,n,100*w/n if n else 0,100*mdd,longs,shorts]
def main():
 print('Downloading',SYMBOL,flush=True);raw=get(SYMBOL);d=prep(raw);d=d.loc[(d.index>=START)&(d.index<END)];s=signal(d)
 periods=[('3Y FULL',START,END),('Y1',pd.Timestamp('2023-09-10',tz='UTC'),pd.Timestamp('2024-09-10',tz='UTC')),('Y2',pd.Timestamp('2024-09-10',tz='UTC'),pd.Timestamp('2025-09-10',tz='UTC')),('Y3',pd.Timestamp('2025-09-10',tz='UTC'),END)]
 rows=[]
 for name,a,b in periods:
  dd=d.loc[(d.index>=a)&(d.index<b)];ss=s.loc[dd.index];r=run(dd,ss,100.);rows.append([name,a.date(),b.date(),round(r[0],2),round(r[0]-100,2),r[1],round(r[2],2),round(r[3],2),r[4],r[5]])
 out=pd.DataFrame(rows,columns=['Period','Start','End','Final_USDT','Return_pct','Trades','WinRate_pct','MaxDD_pct','LongTrades','ShortTrades'])
 print(out.to_string(index=False),flush=True);out.to_csv('backtest_results.csv',index=False)
if __name__=='__main__':main()
