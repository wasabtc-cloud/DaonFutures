#!/usr/bin/env python3
import io, os, math, zipfile, argparse
from datetime import datetime
import requests
import pandas as pd
import numpy as np

BASE='https://data.binance.vision/data/futures/um/monthly/klines/BTCUSDT/5m'
COLS=['open_time','open','high','low','close','volume','close_time','qav','trades','tb_base','tb_quote','ignore']

def months_between(start='2023-09', end='2026-08'):
    y,m=map(int,start.split('-')); ey,em=map(int,end.split('-'))
    out=[]
    while (y,m)<=(ey,em):
        out.append(f'{y}-{m:02d}'); m+=1
        if m==13: y+=1; m=1
    return out

def load_month(ym):
    fn=f'BTCUSDT-5m-{ym}.zip'; url=f'{BASE}/{fn}'
    r=requests.get(url, timeout=60); r.raise_for_status()
    with zipfile.ZipFile(io.BytesIO(r.content)) as z:
        name=z.namelist()[0]
        df=pd.read_csv(z.open(name), header=None, names=COLS)
    for c in ['open','high','low','close','volume']:
        df[c]=pd.to_numeric(df[c], errors='coerce')
    # Binance archives can be ms or us timestamps; normalize.
    ot=pd.to_numeric(df['open_time'], errors='coerce')
    unit='us' if ot.iloc[0] > 10**14 else 'ms'
    df['time']=pd.to_datetime(ot, unit=unit, utc=True)
    return df[['time','open','high','low','close','volume']].dropna()

def load_data(start,end):
    parts=[]
    for ym in months_between(start,end):
        print('DOWNLOAD',ym,flush=True)
        parts.append(load_month(ym))
    df=pd.concat(parts, ignore_index=True).drop_duplicates('time').sort_values('time').reset_index(drop=True)
    return df

def resample(df, rule):
    x=df.set_index('time').resample(rule, label='left', closed='left').agg(
        open=('open','first'), high=('high','max'), low=('low','min'), close=('close','last'), volume=('volume','sum'))
    return x.dropna().reset_index()

def ema(s,n): return s.ewm(span=n, adjust=False).mean()

def add_4h_trend(df, base5):
    h4=resample(base5,'4h')
    h4['ema200']=ema(h4['close'],200)
    h4['trend']=np.where(h4['close']>h4['ema200'],1,np.where(h4['close']<h4['ema200'],-1,0))
    # Only use completed 4H candle: shift one bar then asof merge.
    h4['trend']=h4['trend'].shift(1)
    return pd.merge_asof(df.sort_values('time'), h4[['time','trend']].dropna().sort_values('time'), on='time', direction='backward')

def confirmed_pivots(df,left=3,right=3):
    n=len(df); ph=np.full(n,np.nan); pl=np.full(n,np.nan)
    H=df.high.to_numpy(); L=df.low.to_numpy()
    for i in range(left,n-right):
        if H[i] > np.max(H[i-left:i]) and H[i] >= np.max(H[i+1:i+right+1]):
            ph[i+right]=H[i]  # becomes known only after right bars
        if L[i] < np.min(L[i-left:i]) and L[i] <= np.min(L[i+1:i+right+1]):
            pl[i+right]=L[i]
    return ph,pl

def signal_events(df, combined=False, setup_window=12, fvg_lookback=12):
    x=df.copy().reset_index(drop=True)
    x['ema20']=ema(x.close,20); x['ema50']=ema(x.close,50)
    ph,pl=confirmed_pivots(x,3,3)
    last_ph=np.nan; last_pl=np.nan
    bear_fvgs=[]; bull_fvgs=[]
    active_long=None; active_short=None
    signals=[]
    H=x.high.to_numpy(); L=x.low.to_numpy(); C=x.close.to_numpy()
    for i in range(len(x)):
        if not np.isnan(ph[i]): last_ph=ph[i]
        if not np.isnan(pl[i]): last_pl=pl[i]
        # classic 3-candle FVG, available at close of candle i
        if i>=2:
            if H[i] < L[i-2]:  # bearish gap [H[i], L[i-2]]
                bear_fvgs.append((i,H[i],L[i-2]))
            if L[i] > H[i-2]:  # bullish gap [H[i-2], L[i]]
                bull_fvgs.append((i,H[i-2],L[i]))
        bear_fvgs=[g for g in bear_fvgs if i-g[0] <= fvg_lookback]
        bull_fvgs=[g for g in bull_fvgs if i-g[0] <= fvg_lookback]

        # liquidity sweep: wick through confirmed swing and close back inside
        if not np.isnan(last_pl) and L[i] < last_pl and C[i] > last_pl:
            active_long=(i,last_pl)
        if not np.isnan(last_ph) and H[i] > last_ph and C[i] < last_ph:
            active_short=(i,last_ph)

        if active_long and i-active_long[0] > setup_window: active_long=None
        if active_short and i-active_short[0] > setup_window: active_short=None

        if active_long:
            # inverse bearish FVG: close above upper edge after sweep
            candidates=[g for g in bear_fvgs if g[0] >= active_long[0]-fvg_lookback and C[i] > g[2]]
            if candidates:
                g=candidates[-1]; entry=C[i]; stop=min(g[1], active_long[1])
                if stop < entry:
                    ok=True
                    if combined:
                        ok=(x.loc[i,'ema20']>x.loc[i,'ema50']) and (x.loc[i,'trend']==1)
                    if ok: signals.append((i,'long',entry,stop,'ifvg'))
                active_long=None
        if active_short:
            candidates=[g for g in bull_fvgs if g[0] >= active_short[0]-fvg_lookback and C[i] < g[1]]
            if candidates:
                g=candidates[-1]; entry=C[i]; stop=max(g[2], active_short[1])
                if stop > entry:
                    ok=True
                    if combined:
                        ok=(x.loc[i,'ema20']<x.loc[i,'ema50']) and (x.loc[i,'trend']==-1)
                    if ok: signals.append((i,'short',entry,stop,'ifvg'))
                active_short=None
    return x,signals

def run_backtest(df, combined=False, fee=0.0005, risk_frac=0.01, rr=2.0):
    x,sigs=signal_events(df,combined)
    by_i={}
    for s in sigs: by_i.setdefault(s[0],[]).append(s)
    equity=100.0; peak=equity; maxdd=0.0; trades=[]; inpos=False
    i=0
    while i < len(x)-1:
        if i not in by_i:
            i+=1; continue
        s=by_i[i][0]
        _,side,entry,stop,_=s
        risk_dist=abs(entry-stop)
        if risk_dist<=0 or risk_dist/entry>0.05: i+=1; continue
        target=entry + rr*risk_dist if side=='long' else entry-rr*risk_dist
        risk_dollars=equity*risk_frac
        qty=risk_dollars/risk_dist
        entry_fee=qty*entry*fee
        exit_i=None; exit_price=None; outcome=None
        for j in range(i+1,len(x)):
            hi=float(x.loc[j,'high']); lo=float(x.loc[j,'low'])
            if side=='long':
                hit_sl=lo<=stop; hit_tp=hi>=target
            else:
                hit_sl=hi>=stop; hit_tp=lo<=target
            if hit_sl and hit_tp:
                # conservative same-bar assumption: stop first
                exit_i=j; exit_price=stop; outcome='SL'; break
            if hit_sl:
                exit_i=j; exit_price=stop; outcome='SL'; break
            if hit_tp:
                exit_i=j; exit_price=target; outcome='TP'; break
        if exit_i is None: break
        gross=(exit_price-entry)*qty if side=='long' else (entry-exit_price)*qty
        exit_fee=qty*exit_price*fee
        pnl=gross-entry_fee-exit_fee
        eq0=equity; equity+=pnl; peak=max(peak,equity); maxdd=max(maxdd,(peak-equity)/peak)
        trades.append({'entry_time':x.loc[i,'time'],'exit_time':x.loc[exit_i,'time'],'side':side,'entry':entry,'stop':stop,'target':target,'outcome':outcome,'pnl':pnl,'equity_before':eq0,'equity_after':equity,'stop_pct':risk_dist/entry})
        i=exit_i+1
    t=pd.DataFrame(trades)
    if t.empty:
        return t, {'trades':0,'win_rate':0,'final_equity':equity,'return_pct':0,'max_dd_pct':0,'profit_factor':0,'avg_pnl':0}
    wins=t.pnl[t.pnl>0].sum(); losses=-t.pnl[t.pnl<0].sum()
    return t, {
      'trades':len(t),'win_rate':(t.pnl>0).mean()*100,'final_equity':equity,
      'return_pct':(equity/100-1)*100,'max_dd_pct':maxdd*100,
      'profit_factor':wins/losses if losses>0 else float('inf'),'avg_pnl':t.pnl.mean(),
      'longs':int((t.side=='long').sum()),'shorts':int((t.side=='short').sum())}

def main():
    ap=argparse.ArgumentParser(); ap.add_argument('--start',default='2023-09'); ap.add_argument('--end',default='2026-08'); args=ap.parse_args()
    os.makedirs('backtest_results',exist_ok=True)
    base=load_data(args.start,args.end)
    frames={'5m':base,'15m':resample(base,'15min')}
    rows=[]
    for tf,d in frames.items():
        d=add_4h_trend(d,base)
        for name,combined in [('video_only',False),('video_plus_daon',True)]:
            tr,st=run_backtest(d,combined=combined)
            st.update({'timeframe':tf,'strategy':name,'start':args.start,'end':args.end,'fee_side_pct':0.05,'risk_per_trade_pct':1.0,'rr':2.0})
            rows.append(st)
            tr.to_csv(f'backtest_results/trades_{tf}_{name}.csv',index=False)
            print('RESULT',tf,name,st,flush=True)
    out=pd.DataFrame(rows)
    out.to_csv('backtest_results/summary.csv',index=False)
    print('\n=== SUMMARY ===')
    print(out.to_string(index=False))

if __name__=='__main__': main()
