"""Research benchmark of publicly described bot exit structures.

Sources are documented in comments. These are reference configurations from public
marketplace/docs, not proof of future profitability. The script applies the exit
logic to DaonFutures' existing BLUE->GREEN entries only; no live orders.
"""
from __future__ import annotations

from datetime import datetime, timezone
import numpy as np
import pandas as pd
import natural_prevalence_swing5 as base

MAX_HOLD_MINUTES=360

# Public reference settings collected 2026-09-14:
# Cryptohopper Momentum + Volatility Scalping: TP 5%, SL 1%, trailing 1% armed at 1.5%.
# Cryptohopper Trendhopper: TP 15%, SL 4%, trailing 2% armed at 5%.
# Cryptohopper Daily Trading Profit: bear TP 2.5%, SL 4%; bull TP 4/5/6%, SL 4%.
PROFILES=[
    {'name':'CH_MomentumVolatility','tp':5.0,'sl':1.0,'trail':1.0,'arm':1.5},
    {'name':'CH_Trendhopper','tp':15.0,'sl':4.0,'trail':2.0,'arm':5.0},
    {'name':'CH_DailyBear','tp':2.5,'sl':4.0,'trail':None,'arm':None},
    {'name':'CH_DailyBull4','tp':4.0,'sl':4.0,'trail':None,'arm':None},
    {'name':'CH_DailyBull5','tp':5.0,'sl':4.0,'trail':None,'arm':None},
    {'name':'CH_DailyBull6','tp':6.0,'sl':4.0,'trail':None,'arm':None},
]


def simulate(path,entry,p):
    hard_stop=entry*(1-p['sl']/100)
    tp=entry*(1+p['tp']/100)
    armed=False; peak=entry; active_stop=hard_stop
    if path.empty:return np.nan,'no_path'
    for _,bar in path.iterrows():
        lo=float(bar.low); hi=float(bar.high)
        # Conservative ordering for 1m OHLC ambiguity: protective stop is checked first.
        if lo<=active_stop:
            return (active_stop/entry-1)*100,'trail_or_stop' if armed else 'stop'
        if hi>=tp:
            return p['tp'],'take_profit'
        if p['trail'] is not None:
            if hi>=entry*(1+p['arm']/100):
                armed=True
            if armed:
                peak=max(peak,hi)
                active_stop=max(hard_stop,peak*(1-p['trail']/100))
                # If this candle also spans below the newly raised trail, assume worst case.
                if lo<=active_stop:
                    return (active_stop/entry-1)*100,'trail'
    close=float(path.close.iloc[-1])
    return (close/entry-1)*100,'time_exit'


def summary(g):
    r=g.net_pct.astype(float); gp=r[r>0].sum(); gl=-r[r<0].sum()
    eq=(1+r/100).cumprod()*100; peak=eq.cummax(); mdd=((eq/peak)-1).min()*-100
    return pd.Series({
        'trades':len(g),'win_rate_pct':(r>0).mean()*100,'avg_trade_pct':r.mean(),
        'median_trade_pct':r.median(),'profit_factor':gp/gl if gl>0 else np.inf,
        'mdd_pct':mdd,'ending_equity_from_100':float(eq.iloc[-1]),
        'tp_hit_pct':(g.exit_reason=='take_profit').mean()*100,
        'stop_or_trail_pct':g.exit_reason.isin(['stop','trail','trail_or_stop']).mean()*100,
        'time_exit_pct':(g.exit_reason=='time_exit').mean()*100,
    })


def main():
    end=pd.Timestamp(datetime.now(timezone.utc)).floor('D')
    markets=[x['market'] for x in base.get('/market/all',{'is_details':'false'}) if x['market'].startswith('KRW-')]
    cols,stats,w,th,train_cut=base.train_model(markets,end)
    valid_start=max(train_cut+pd.Timedelta(days=1),end-pd.Timedelta(days=base.VALID_DAYS))
    universe=base.market_universe(markets,valid_start)
    rows=[]
    for ix,m in enumerate(universe,1):
        print(f'EXTERNAL EXIT {ix}/{len(universe)} {m}',flush=True)
        raw=base.fetch_continuous_minutes(m,valid_start-pd.Timedelta(minutes=150),end)
        d=base.features(raw,valid_start)
        if d.empty:continue
        d['score']=base.score_frame(d,cols,stats,w); idx=d.index; i=0
        while i<len(d)-2:
            if d.score.iloc[i]<th:i+=1;continue
            bt=idx[i]; j=i; limit=bt+pd.Timedelta(minutes=base.GREEN_WINDOW); green=None
            while j<len(d) and idx[j]<=limit:
                row=d.iloc[j]
                if row.value5_ratio>=base.GREEN_VALUE5 and row.value_accel5>=base.GREEN_ACCEL5 and row.ret5>0 and row.ret15>0:
                    green=j; break
                j+=1
            if green is None:i=j+1;continue
            if green+1>=len(d):break
            entry_time=idx[green+1]; entry=float(d.open.iloc[green+1])*(1+base.SLIP)
            path=raw.loc[(raw.index>=entry_time)&(raw.index<=entry_time+pd.Timedelta(minutes=MAX_HOLD_MINUTES))]
            if path.empty:i+=1;continue
            for p in PROFILES:
                gross,reason=simulate(path,entry,p)
                drag=(2*base.FEE+2*base.SLIP)*100
                rows.append({'market':m,'entry_time':entry_time,'profile':p['name'],'gross_pct':gross,'net_pct':gross-drag,'exit_reason':reason})
            i=int(idx.searchsorted(entry_time+pd.Timedelta(minutes=MAX_HOLD_MINUTES),side='left'))
    tr=pd.DataFrame(rows)
    if tr.empty:raise RuntimeError('no external exit benchmark trades')
    tr=tr.sort_values('entry_time').reset_index(drop=True)
    tr.to_csv('external_exit_profile_trades.csv',index=False)
    out=tr.groupby('profile',sort=False).apply(summary,include_groups=False).reset_index()
    out=out.sort_values(['profit_factor','ending_equity_from_100'],ascending=False)
    out.to_csv('external_exit_profile_summary.csv',index=False)
    print(out.to_string(index=False),flush=True)

if __name__=='__main__':main()
