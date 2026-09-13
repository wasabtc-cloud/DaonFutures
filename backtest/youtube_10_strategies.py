import pandas as pd, numpy as np, requests, time
from datetime import datetime, timezone, timedelta

SYMBOL='BTCUSDT'; INTERVAL='15m'; YEARS=3; FEE=.0005; SLIP=.0002
URL='https://fapi.binance.com/fapi/v1/klines'

def get_data():
    end=int(datetime.now(timezone.utc).timestamp()*1000); start=int((datetime.now(timezone.utc)-timedelta(days=365*YEARS)).timestamp()*1000)
    out=[]; cur=start
    while cur<end:
        r=requests.get(URL,params={'symbol':SYMBOL,'interval':INTERVAL,'startTime':cur,'endTime':end,'limit':1500},timeout=30); r.raise_for_status(); x=r.json()
        if not x: break
        out+=x; cur=x[-1][0]+1; time.sleep(.03)
    d=pd.DataFrame(out,columns=['t','o','h','l','c','v','ct','q','n','tb','tq','i'])
    for c in ['o','h','l','c','v']: d[c]=pd.to_numeric(d[c])
    d['dt']=pd.to_datetime(d.t,unit='ms',utc=True); d=d.drop_duplicates('t').set_index('dt')
    return d

def ind(d):
    d=d.copy(); d['ema20']=d.c.ewm(span=20,adjust=False).mean(); d['ema50']=d.c.ewm(span=50,adjust=False).mean(); d['ema200']=d.c.ewm(span=200,adjust=False).mean()
    d['atr']=pd.concat([(d.h-d.l),(d.h-d.c.shift()).abs(),(d.l-d.c.shift()).abs()],axis=1).max(axis=1).rolling(14).mean()
    d['volma']=d.v.rolling(20).mean(); d['hh20']=d.h.shift(1).rolling(20).max(); d['ll20']=d.l.shift(1).rolling(20).min(); d['hh50']=d.h.shift(1).rolling(50).max(); d['ll50']=d.l.shift(1).rolling(50).min()
    d['mid20']=d.c.rolling(20).mean(); d['std20']=d.c.rolling(20).std(); d['bbup']=d.mid20+2*d.std20; d['bblo']=d.mid20-2*d.std20; d['bbw']=(d.bbup-d.bblo)/d.mid20
    tp=(d.h+d.l+d.c)/3; day=d.index.floor('D'); d['vwap']=(tp*d.v).groupby(day).cumsum()/d.v.groupby(day).cumsum()
    d['ph']=d.h.shift(1).rolling(12).max(); d['pl']=d.l.shift(1).rolling(12).min()
    return d

def signals(d,k):
    long=pd.Series(False,index=d.index); short=long.copy()
    if k==1: # breakout retest proxy: prior 20 high/low break with volume
        long=(d.c>d.hh20)&(d.v>1.2*d.volma); short=(d.c<d.ll20)&(d.v>1.2*d.volma)
    elif k==2: # S/R flip retest: wick through prior level and close back trend side
        long=(d.l<=d.hh20)&(d.c>d.hh20)&(d.c>d.ema200); short=(d.h>=d.ll20)&(d.c<d.ll20)&(d.c<d.ema200)
    elif k==3: # liquidity sweep reversal
        long=(d.l<d.pl)&(d.c>d.pl)&(d.c>d.o); short=(d.h>d.ph)&(d.c<d.ph)&(d.c<d.o)
    elif k==4: # liquidity sweep + displacement/FVG proxy
        long=(d.l.shift(1)<d.pl.shift(1))&(d.c.shift(1)>d.pl.shift(1))&(d.c>d.h.shift(1))&(d.c>d.ema20); short=(d.h.shift(1)>d.ph.shift(1))&(d.c.shift(1)<d.ph.shift(1))&(d.c<d.l.shift(1))&(d.c<d.ema20)
    elif k==5: # order-block style pullback in trend
        long=(d.ema20>d.ema50)&(d.l<d.ema20)&(d.c>d.ema20)&(d.c>d.o); short=(d.ema20<d.ema50)&(d.h>d.ema20)&(d.c<d.ema20)&(d.c<d.o)
    elif k==6: # VWAP reclaim/reject
        long=(d.l<d.vwap)&(d.c>d.vwap)&(d.c>d.ema200); short=(d.h>d.vwap)&(d.c<d.vwap)&(d.c<d.ema200)
    elif k==7: # Donchian 50 breakout
        long=(d.c>d.hh50)&(d.c>d.ema200); short=(d.c<d.ll50)&(d.c<d.ema200)
    elif k==8: # Bollinger squeeze breakout
        squeeze=d.bbw<d.bbw.rolling(100).quantile(.2); long=squeeze.shift(1)&(d.c>d.bbup)&(d.c>d.ema200); short=squeeze.shift(1)&(d.c<d.bblo)&(d.c<d.ema200)
    elif k==9: # EMA trend pullback + S/R
        long=(d.ema20>d.ema50)&(d.c>d.ema200)&(d.l<d.ema20)&(d.c>d.ema20); short=(d.ema20<d.ema50)&(d.c<d.ema200)&(d.h>d.ema20)&(d.c<d.ema20)
    elif k==10: # false breakout / failed breakout
        long=(d.l<d.ll20)&(d.c>d.ll20)&(d.v>d.volma); short=(d.h>d.hh20)&(d.c<d.hh20)&(d.v>d.volma)
    return long.fillna(False),short.fillna(False)

def bt(d,L,S):
    eq=100.; peak=100.; mdd=0.; rs=[]; pos=0; ent=sl=tp=0
    for i in range(210,len(d)-1):
        r=d.iloc[i]
        if pos:
            hit_sl=(r.l<=sl if pos==1 else r.h>=sl); hit_tp=(r.h>=tp if pos==1 else r.l<=tp)
            if hit_sl or hit_tp:
                ex=sl if hit_sl else tp; ret=(ex/ent-1)*pos-(FEE+SLIP)*2; eq*=1+ret; rs.append(ret); peak=max(peak,eq); mdd=max(mdd,(peak-eq)/peak); pos=0
        if not pos and (L.iloc[i] or S.iloc[i]) and np.isfinite(r.atr) and r.atr>0:
            pos=1 if L.iloc[i] else -1; ent=d.iloc[i+1].o*(1+SLIP*pos); risk=1.5*r.atr; sl=ent-risk*pos; tp=ent+2*risk*pos
    wins=[x for x in rs if x>0]; losses=[x for x in rs if x<0]; pf=sum(wins)/abs(sum(losses)) if losses else np.inf
    return {'trades':len(rs),'win_rate':100*len(wins)/len(rs) if rs else 0,'return_pct':eq-100,'PF':pf,'MDD_pct':100*mdd}

names=['Breakout+Volume','S/R Flip Retest','Liquidity Sweep','Sweep+Displacement/FVG','OrderBlock Pullback','VWAP Reclaim','Donchian50 Breakout','Bollinger Squeeze Breakout','EMA Trend Pullback','Failed Breakout Reversal']
d=ind(get_data()); rows=[]
for k,n in enumerate(names,1):
    L,S=signals(d,k); z=bt(d,L,S); z.update(strategy=n,id=k); rows.append(z); print(n,z)
pd.DataFrame(rows).sort_values(['PF','return_pct'],ascending=False).to_csv('youtube_10_results.csv',index=False)
