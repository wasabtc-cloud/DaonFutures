"""Research-only TP/SL grid analysis for DaonFutures entry signals.

Reuses the existing BLUE->GREEN entry logic and tests multiple fixed stop/take-profit
structures plus the current structural SWING10 stop. No live orders are placed.
"""
from __future__ import annotations

import numpy as np
import pandas as pd
from datetime import datetime, timezone

import natural_prevalence_swing5 as base

TP_PCTS=(1.0,1.5,2.0,3.0,5.0,7.5,10.0)
SL_PCTS=(0.5,0.75,1.0,1.5,2.0,3.0,5.0)
MAX_HOLD_MINUTES=360


def simulate_fixed(path, entry, tp_pct, sl_pct):
    tp=entry*(1+tp_pct/100.0)
    sl=entry*(1-sl_pct/100.0)
    if path.empty:return np.nan,'no_path'
    for _,row in path.iterrows():
        lo=float(row.low); hi=float(row.high)
        # Conservative same-bar assumption: stop first if both touched.
        if lo<=sl and hi>=tp:return -sl_pct,'both_stop_first'
        if lo<=sl:return -sl_pct,'stop'
        if hi>=tp:return tp_pct,'take_profit'
    close=float(path.close.iloc[-1])
    return (close/entry-1)*100.0,'time_exit'


def summarize(df,tp,sl):
    if df.empty:return {'tp_pct':tp,'sl_pct':sl,'trades':0}
    r=df.net_pct.astype(float)
    gp=r[r>0].sum(); gl=-r[r<0].sum()
    eq=(1+r/100.0).cumprod()*100.0
    peak=eq.cummax(); mdd=((eq/peak)-1).min()*-100.0
    return {
        'tp_pct':tp,'sl_pct':sl,'trades':len(df),
        'win_rate_pct':(r>0).mean()*100.0,
        'avg_trade_pct':r.mean(),
        'median_trade_pct':r.median(),
        'profit_factor':gp/gl if gl>0 else np.inf,
        'mdd_pct':mdd,
        'ending_equity_from_100':float(eq.iloc[-1]),
        'tp_hit_pct':(df.exit_reason=='take_profit').mean()*100.0,
        'stop_hit_pct':df.exit_reason.isin(['stop','both_stop_first']).mean()*100.0,
        'time_exit_pct':(df.exit_reason=='time_exit').mean()*100.0,
    }


def main():
    end=pd.Timestamp(datetime.now(timezone.utc)).floor('D')
    markets=[x['market'] for x in base.get('/market/all',{'is_details':'false'}) if x['market'].startswith('KRW-')]
    cols,stats,w,th,train_cut=base.train_model(markets,end)
    valid_start=max(train_cut+pd.Timedelta(days=1),end-pd.Timedelta(days=base.VALID_DAYS))
    universe=base.market_universe(markets,valid_start)

    rows=[]
    for ix,m in enumerate(universe,1):
        print(f'TPSL {ix}/{len(universe)} {m}',flush=True)
        raw=base.fetch_continuous_minutes(m,valid_start-pd.Timedelta(minutes=150),end)
        d=base.features(raw,valid_start)
        if d.empty:continue
        d['swing10']=raw.low.shift(1).rolling(10).min().reindex(d.index)
        d=d.dropna(subset=['swing10'])
        if d.empty:continue
        d['score']=base.score_frame(d,cols,stats,w); idx=d.index; i=0
        while i<len(d)-2:
            if d.score.iloc[i]<th:i+=1;continue
            bt=idx[i]; j=i; limit=bt+pd.Timedelta(minutes=base.GREEN_WINDOW); green=None
            while j<len(d) and idx[j]<=limit:
                row=d.iloc[j]
                if row.value5_ratio>=base.GREEN_VALUE5 and row.value_accel5>=base.GREEN_ACCEL5 and row.ret5>0 and row.ret15>0:
                    green=j;break
                j+=1
            if green is None:i=j+1;continue
            if green+1>=len(d):break
            entry_time=idx[green+1]; entry=float(d.open.iloc[green+1])*(1+base.SLIP)
            path=raw.loc[(raw.index>=entry_time)&(raw.index<=entry_time+pd.Timedelta(minutes=MAX_HOLD_MINUTES))]
            if path.empty:i+=1;continue

            for tp in TP_PCTS:
                for sl in SL_PCTS:
                    gross,reason=simulate_fixed(path,entry,tp,sl)
                    # Approximate round-trip fee/slippage drag using existing constants.
                    drag_pct=(2*base.FEE+2*base.SLIP)*100.0
                    net=gross-drag_pct
                    rows.append({'market':m,'entry_time':entry_time,'tp_pct':tp,'sl_pct':sl,'gross_pct':gross,'net_pct':net,'exit_reason':reason})
            i=int(idx.searchsorted(entry_time+pd.Timedelta(minutes=MAX_HOLD_MINUTES),side='left'))

    trades=pd.DataFrame(rows)
    if trades.empty:raise RuntimeError('no TP/SL research trades')
    trades.to_csv('tp_sl_grid_trades.csv',index=False)
    summary=[]
    for tp in TP_PCTS:
        for sl in SL_PCTS:
            summary.append(summarize(trades[(trades.tp_pct==tp)&(trades.sl_pct==sl)],tp,sl))
    out=pd.DataFrame(summary).sort_values(['profit_factor','ending_equity_from_100'],ascending=False)
    out.to_csv('tp_sl_grid_summary.csv',index=False)
    print(out.head(20).to_string(index=False),flush=True)

if __name__=='__main__':main()
