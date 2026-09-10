import math, time, json, urllib.parse, urllib.request
from datetime import datetime, timezone
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt

START='2025-09-10'
END='2026-09-10'
SYMBOLS=['BTCUSDT','ETHUSDT']
START_BAL=100.0
SL_PCT=0.01
TP_PCT=0.015
FEE_RATE=0.0005  # taker fee per side assumption


def get_klines(symbol, interval, start_ms, end_ms):
    rows=[]
    cur=start_ms
    while cur<end_ms:
        qs=urllib.parse.urlencode({'symbol':symbol,'interval':interval,'limit':1500,'startTime':cur,'endTime':end_ms})
        url='https://fapi.binance.com/fapi/v1/klines?'+qs
        with urllib.request.urlopen(url, timeout=30) as r:
            data=json.loads(r.read().decode())
        if not data: break
        rows.extend(data)
        nxt=data[-1][6]+1
        if nxt<=cur: break
        cur=nxt
        time.sleep(0.08)
    cols=['open_time','open','high','low','close','volume','close_time','qv','trades','tb','tq','ignore']
    df=pd.DataFrame(rows,columns=cols)
    for c in ['open','high','low','close','volume']: df[c]=df[c].astype(float)
    df['open_time']=pd.to_datetime(df['open_time'],unit='ms',utc=True)
    df=df.drop_duplicates('open_time').set_index('open_time').sort_index()
    return df[['open','high','low','close','volume']]


def ema(s,n): return s.ewm(span=n,adjust=False).mean()

def rsi(s,n=14):
    d=s.diff(); up=d.clip(lower=0); dn=-d.clip(upper=0)
    ag=up.ewm(alpha=1/n,adjust=False).mean(); al=dn.ewm(alpha=1/n,adjust=False).mean()
    rs=ag/al.replace(0,np.nan)
    out=100-100/(1+rs)
    return out.fillna(100)

def atr(df,n=10):
    pc=df.close.shift(1)
    tr=pd.concat([(df.high-df.low),(df.high-pc).abs(),(df.low-pc).abs()],axis=1).max(axis=1)
    return tr.ewm(alpha=1/n,adjust=False).mean()

def supertrend(df,period=10,mult=3.0):
    hl2=(df.high+df.low)/2
    a=atr(df,period)
    ub=hl2+mult*a; lb=hl2-mult*a
    fub=ub.copy(); flb=lb.copy(); trend=pd.Series(index=df.index,dtype=int)
    trend.iloc[0]=1
    for i in range(1,len(df)):
        fub.iloc[i]=ub.iloc[i] if (ub.iloc[i]<fub.iloc[i-1] or df.close.iloc[i-1]>fub.iloc[i-1]) else fub.iloc[i-1]
        flb.iloc[i]=lb.iloc[i] if (lb.iloc[i]>flb.iloc[i-1] or df.close.iloc[i-1]<flb.iloc[i-1]) else flb.iloc[i-1]
        if df.close.iloc[i]>fub.iloc[i-1]: trend.iloc[i]=1
        elif df.close.iloc[i]<flb.iloc[i-1]: trend.iloc[i]=-1
        else: trend.iloc[i]=trend.iloc[i-1]
    return trend

def prep(df15):
    d=df15.copy()
    d['ema20']=ema(d.close,20); d['ema50']=ema(d.close,50); d['rsi']=rsi(d.close,14); d['vma20']=d.volume.rolling(20).mean()
    h1=d.resample('1h',label='right',closed='right').agg({'open':'first','high':'max','low':'min','close':'last','volume':'sum'}).dropna()
    h4=d.resample('4h',label='right',closed='right').agg({'open':'first','high':'max','low':'min','close':'last','volume':'sum'}).dropna()
    h1['ema20']=ema(h1.close,20); h1['ema50']=ema(h1.close,50); h1['st']=supertrend(h1,10,3.0)
    h4['ema20']=ema(h4.close,20); h4['ema50']=ema(h4.close,50); h4['ema200']=ema(h4.close,200)
    d=d.join(h1[['ema20','ema50','st']].rename(columns={'ema20':'h1e20','ema50':'h1e50','st':'h1st'}),how='left').ffill()
    d=d.join(h4[['ema20','ema50','ema200']].rename(columns={'ema20':'h4e20','ema50':'h4e50','ema200':'h4e200'}),how='left').ffill()
    return d

def signals_current(d):
    prev_ema20=d.ema20.shift(1)
    long_pull=(d.low.shift(1)<=prev_ema20)&(d.close>d.ema20)
    short_pull=(d.high.shift(1)>=prev_ema20)&(d.close<d.ema20)
    long=(d.h4e20>d.h4e50)&(d.h1e20>d.h1e50)&long_pull&(d.rsi>=50)
    short=(d.h4e20<d.h4e50)&(d.h1e20<d.h1e50)&short_pull&(d.rsi<=50)
    return pd.Series(np.where(long,1,np.where(short,-1,0)),index=d.index)

def signals_recommended(d):
    cross_up=(d.close>d.ema20)&(d.close.shift(1)<=d.ema20.shift(1))
    cross_dn=(d.close<d.ema20)&(d.close.shift(1)>=d.ema20.shift(1))
    vol=d.volume>d.vma20
    long=(d.close>d.ema20)&(d.ema20>d.ema50)&(d.h4e200<d.close)&(d.h1st==1)&cross_up&vol&(d.rsi>=50)&(d.rsi<=70)
    short=(d.close<d.ema20)&(d.ema20<d.ema50)&(d.h4e200>d.close)&(d.h1st==-1)&cross_dn&vol&(d.rsi<=50)&(d.rsi>=30)
    return pd.Series(np.where(long,1,np.where(short,-1,0)),index=d.index)

def run_bt(d,sig):
    bal=START_BAL; peak=bal; maxdd=0; trades=[]; eq=[(d.index[0],bal)]
    i=0
    while i<len(d)-1:
        side=int(sig.iloc[i])
        if side==0 or not np.isfinite(d.close.iloc[i]): i+=1; continue
        entry=d.close.iloc[i]; sl=entry*(1-SL_PCT) if side==1 else entry*(1+SL_PCT); tp=entry*(1+TP_PCT) if side==1 else entry*(1-TP_PCT)
        j=i+1; outcome=None; exitp=None
        while j<len(d):
            hi=d.high.iloc[j]; lo=d.low.iloc[j]
            hit_sl=(lo<=sl) if side==1 else (hi>=sl)
            hit_tp=(hi>=tp) if side==1 else (lo<=tp)
            if hit_sl and hit_tp: outcome='SL'; exitp=sl; break
            if hit_sl: outcome='SL'; exitp=sl; break
            if hit_tp: outcome='TP'; exitp=tp; break
            j+=1
        if outcome is None: break
        gross=(exitp/entry-1)*side
        net=gross-2*FEE_RATE
        pnl=bal*net
        before=bal; bal+=pnl
        peak=max(peak,bal); maxdd=max(maxdd,(peak-bal)/peak)
        trades.append((d.index[i],d.index[j],side,before,bal,outcome,net))
        eq.append((d.index[j],bal)); i=j+1
    wins=sum(1 for t in trades if t[5]=='TP'); n=len(trades); losses=n-wins
    gross_profit=sum(max(0,(t[4]-t[3])) for t in trades); gross_loss=-sum(min(0,(t[4]-t[3])) for t in trades)
    pf=gross_profit/gross_loss if gross_loss>0 else float('inf')
    return {'final':bal,'return_pct':(bal/START_BAL-1)*100,'trades':n,'wins':wins,'losses':losses,'winrate':wins/n*100 if n else 0,'pf':pf,'maxdd':maxdd*100,'equity':eq}

def main():
    start_ms=int(pd.Timestamp(START,tz='UTC').timestamp()*1000); end_ms=int(pd.Timestamp(END,tz='UTC').timestamp()*1000)
    results=[]
    fig,axes=plt.subplots(2,1,figsize=(12,12))
    for ax,sym in zip(axes,SYMBOLS):
        print('Downloading',sym,flush=True)
        d=prep(get_klines(sym,'15m',start_ms,end_ms))
        warm=d.index>=pd.Timestamp(START,tz='UTC')+pd.Timedelta(days=35)
        d=d.loc[warm]
        for name,fn in [('Current app',signals_current),('Recommended',signals_recommended)]:
            bt=run_bt(d,fn(d)); results.append((sym,name,bt))
            x=[a for a,b in bt['equity']]; y=[b for a,b in bt['equity']]
            ax.plot(x,y,label=f"{name}  ${bt['final']:.2f}  WR {bt['winrate']:.1f}%")
        ax.axhline(100,ls='--',lw=1,alpha=.5); ax.set_title(sym+' — 1Y backtest'); ax.set_ylabel('Equity (USDT)'); ax.grid(alpha=.2); ax.legend()
    fig.suptitle('DaonFutures strategy comparison — Start $100, SL 1.0%, TP 1.5% (R:R 1:1.5)\nBinance USD-M Futures 15m, 2025-09-10 to 2026-09-10, fee 0.05% each side',fontsize=14)
    plt.tight_layout(rect=[0,0,1,.95]); plt.savefig('backtest_equity.png',dpi=180,bbox_inches='tight')
    rows=[]
    for sym,name,bt in results:
        rows.append({'Symbol':sym,'Strategy':name,'Final_USDT':round(bt['final'],2),'Return_pct':round(bt['return_pct'],2),'Trades':bt['trades'],'WinRate_pct':round(bt['winrate'],2),'ProfitFactor':round(bt['pf'],2) if math.isfinite(bt['pf']) else 999,'MaxDD_pct':round(bt['maxdd'],2)})
    pd.DataFrame(rows).to_csv('backtest_results.csv',index=False)
    print(pd.DataFrame(rows).to_string(index=False))

if __name__=='__main__': main()
