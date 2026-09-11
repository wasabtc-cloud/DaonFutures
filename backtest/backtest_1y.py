import io,zipfile,urllib.request
from datetime import date,timedelta
import pandas as pd
import numpy as np
SYMBOL='ETHUSDT';INTERVAL='15m';FEE=.0005;SL=.01;TP=.02;LEV=3
START=pd.Timestamp('2023-09-10',tz='UTC');END=pd.Timestamp('2026-09-10',tz='UTC')
def rz(url):
 try:
  with urllib.request.urlopen(url,timeout=60) as r:raw=r.read()
  with zipfile.ZipFile(io.BytesIO(raw)) as z:return pd.read_csv(z.open(z.namelist()[0]),header=None)
 except Exception:return pd.DataFrame()
def get():
 p=[];y,m=2023,8
 while (y,m)<=(2026,8):
  x=rz(f'https://data.binance.vision/data/futures/um/monthly/klines/{SYMBOL}/{INTERVAL}/{SYMBOL}-{INTERVAL}-{y}-{m:02d}.zip')
  if not x.empty:p.append(x)
  m+=1
  if m==13:y+=1;m=1
 d=date(2026,9,1)
 while d<date(2026,9,10):
  x=rz(f'https://data.binance.vision/data/futures/um/daily/klines/{SYMBOL}/{INTERVAL}/{SYMBOL}-{INTERVAL}-{d.isoformat()}.zip')
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
def supertrend(d,n=10,k=3):
 a=atr(d,n);hl=(d.high+d.low)/2;ub=hl+k*a;lb=hl-k*a;fu=ub.copy();fl=lb.copy();trend=pd.Series(1,index=d.index,dtype=int);line=pd.Series(np.nan,index=d.index)
 for i in range(1,len(d)):
  fu.iloc[i]=ub.iloc[i] if ub.iloc[i]<fu.iloc[i-1] or d.close.iloc[i-1]>fu.iloc[i-1] else fu.iloc[i-1]
  fl.iloc[i]=lb.iloc[i] if lb.iloc[i]>fl.iloc[i-1] or d.close.iloc[i-1]<fl.iloc[i-1] else fl.iloc[i-1]
  trend.iloc[i]=1 if d.close.iloc[i]>fu.iloc[i-1] else (-1 if d.close.iloc[i]<fl.iloc[i-1] else trend.iloc[i-1])
  line.iloc[i]=fl.iloc[i] if trend.iloc[i]==1 else fu.iloc[i]
 return trend,line
def adx(d,n=14):
 u=d.high.diff();dn=-d.low.diff();p=pd.Series(np.where((u>dn)&(u>0),u,0.),index=d.index);m=pd.Series(np.where((dn>u)&(dn>0),dn,0.),index=d.index);a=atr(d,n);pi=100*p.ewm(alpha=1/n,adjust=False).mean()/a;mi=100*m.ewm(alpha=1/n,adjust=False).mean()/a;dx=100*(pi-mi).abs()/(pi+mi).replace(0,np.nan);return dx.ewm(alpha=1/n,adjust=False).mean()
def prep(d):
 d=d.copy();d['e20']=ema(d.close,20);d['e50']=ema(d.close,50);d['rsi']=rsi(d.close);d['vma']=d.volume.rolling(20).mean()
 # 15m Supertrend is used only as the runner exit after +2% partial TP.
 d['st15'],d['st15line']=supertrend(d)
 h1=d.resample('1h',label='right',closed='right').agg({'open':'first','high':'max','low':'min','close':'last','volume':'sum'}).dropna();h4=d.resample('4h',label='right',closed='right').agg({'open':'first','high':'max','low':'min','close':'last','volume':'sum'}).dropna()
 h1['st'],_=supertrend(h1);h1['adx']=adx(h1);h4['e200']=ema(h4.close,200);h4['slope6']=(h4.e200-h4.e200.shift(6))/h4.e200.shift(6)
 return d.join(h1[['st','adx']].rename(columns={'st':'h1st','adx':'h1adx'})).ffill().join(h4[['e200','slope6']].rename(columns={'e200':'h4e200','slope6':'h4slope'})).ffill()
def signals(d):
 cu=(d.close>d.e20)&(d.close.shift()<=d.e20.shift());cd=(d.close<d.e20)&(d.close.shift()>=d.e20.shift());vr=d.volume/d.vma
 L=(d.e20>d.e50)&(d.h1st==1)&cu&d.rsi.between(50,70)&(d.close>d.h4e200)&(vr>=1.2)&(d.h1adx>=25)&(d.h4slope>=.001)
 S=(d.e20<d.e50)&(d.h1st==-1)&cd&d.rsi.between(30,50)&(d.close<d.h4e200)&(vr>=1.0)&(d.h1adx>=30)&(d.h4slope<=0)
 return pd.Series(np.where(L,1,np.where(S,-1,0)),index=d.index)
def run(d,s,variant):
 bal=100.;peak=100.;mdd=0.;n=w=0;gp=gl=0.;i=0
 while i<len(d)-1 and bal>1:
  side=int(s.iloc[i])
  if not side:i+=1;continue
  e=d.close.iloc[i];stop=e*(1-SL) if side==1 else e*(1+SL);take=e*(1+TP) if side==1 else e*(1-TP);j=i+1;partial=False;ret=0.;fees=0.
  while j<len(d):
   hs=d.low.iloc[j]<=stop if side==1 else d.high.iloc[j]>=stop
   ht=d.high.iloc[j]>=take if side==1 else d.low.iloc[j]<=take
   if not partial:
    if hs:
     ret=((stop/e-1)*side);fees=2*FEE;break
    if ht:
     if variant=='TP2_FULL':ret=((take/e-1)*side);fees=2*FEE;break
     partial=True;ret=.5*((take/e-1)*side);fees=FEE+.5*FEE
     if variant=='TP2_HALF_BE_ST':stop=e
     j+=1;continue
   else:
    # Remaining 50% exits at breakeven/original SL first, or when price touches 15m Supertrend line / trend flips.
    hs=d.low.iloc[j]<=stop if side==1 else d.high.iloc[j]>=stop
    line=d.st15line.iloc[j];touch=(d.low.iloc[j]<=line if side==1 else d.high.iloc[j]>=line) if pd.notna(line) else False
    flip=(d.st15.iloc[j]!=side)
    if hs:
     ret+=.5*((stop/e-1)*side);fees+=.5*FEE;break
    if touch or flip:
     x=line if touch and pd.notna(line) else d.close.iloc[j]
     # Prevent impossible favorable fill if line lies beyond candle range.
     x=min(max(x,d.low.iloc[j]),d.high.iloc[j])
     ret+=.5*((x/e-1)*side);fees+=.5*FEE;break
   j+=1
  if j>=len(d):break
  before=bal;r=(ret-fees)*LEV;bal*=max(0,1+r);pnl=bal-before;gp+=max(0,pnl);gl+=max(0,-pnl);peak=max(peak,bal);mdd=max(mdd,(peak-bal)/peak);n+=1;w+=int(pnl>0);i=j+1
 return bal,n,100*w/n if n else 0,(gp/gl if gl else 999),100*mdd
def main():
 print('Downloading ETHUSDT 15m',flush=True);d=prep(get());d=d.loc[(d.index>=START)&(d.index<END)];s=signals(d)
 years=[('Y1','2023-09-10','2024-09-10'),('Y2','2024-09-10','2025-09-10'),('Y3','2025-09-10','2026-09-10')]
 variants=['TP2_FULL','TP2_HALF_ST','TP2_HALF_BE_ST'];rows=[]
 for v in variants:
  f=run(d,s,v);ys=[]
  for _,a,b in years:
   dd=d.loc[(d.index>=pd.Timestamp(a,tz='UTC'))&(d.index<pd.Timestamp(b,tz='UTC'))];ys.append(run(dd,s.loc[dd.index],v)[0])
  rows.append([v,round(f[0],2),round(f[0]-100,2),f[1],round(f[2],2),round(f[3],2),round(f[4],2),*[round(x,2) for x in ys]])
 out=pd.DataFrame(rows,columns=['Exit','Final3Y','Return3Y_pct','Trades','WinRate_pct','PF','MDD_pct','Y1_Final','Y2_Final','Y3_Final']).sort_values('Final3Y',ascending=False)
 print(out.to_string(index=False),flush=True);out.to_csv('backtest_results.csv',index=False)
if __name__=='__main__':main()
