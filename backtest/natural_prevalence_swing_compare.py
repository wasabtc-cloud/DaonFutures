"""Fair SWING5/10/20 comparison.

Reuses the exact natural-prevalence model, universe, fees, slippage and exits.
Only the initial structural stop lookback changes: 5, 10, or 20 completed 1m lows.
This avoids changing multiple variables at once.
"""
import pandas as pd
import numpy as np
import natural_prevalence_swing5 as base
from datetime import datetime, timezone

SWINGS=(5,10,20)

def add_swings(raw,start):
    d=base.features(raw,start)
    for n in SWINGS:
        d[f'swing{n}']=raw.low.shift(1).rolling(n).min().reindex(d.index)
    return d.dropna(subset=[f'swing{n}' for n in SWINGS])

def summarize(tr,n):
    if tr.empty:return {'swing':n,'trades':0}
    r=tr.result_r.astype(float); gp=r[r>0].sum(); gl=-r[r<0].sum(); mdd,end=base.max_dd(r.values)
    return {'swing':n,'trades':len(tr),'win_rate_pct':(r>0).mean()*100,'avg_r':r.mean(),'median_r':r.median(),'profit_factor_r':gp/gl if gl>0 else np.inf,'mdd_pct_at_1pct_risk':mdd,'ending_equity_at_1pct_risk':end,'max_consecutive_losses':base.loss_streak(r.values),'positive_2r_plus_pct':(r>=2).mean()*100,'avg_risk_pct':tr.risk_pct.mean()}

def main():
    end=pd.Timestamp(datetime.now(timezone.utc)).floor('D')
    markets=[x['market'] for x in base.get('/market/all',{'is_details':'false'}) if x['market'].startswith('KRW-')]
    cols,stats,w,th,train_cut=base.train_model(markets,end)
    valid_start=max(train_cut+pd.Timedelta(days=1),end-pd.Timedelta(days=base.VALID_DAYS))
    universe=base.market_universe(markets,valid_start)
    buckets={n:[] for n in SWINGS}
    for ix,m in enumerate(universe,1):
        print(f'COMPARE {ix}/{len(universe)} {m}',flush=True)
        raw=base.fetch_continuous_minutes(m,valid_start-pd.Timedelta(minutes=150),end)
        d=add_swings(raw,valid_start)
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
            path=raw.loc[(raw.index>=entry_time)&(raw.index<=entry_time+pd.Timedelta(minutes=base.HORIZON_MINUTES))]
            for n in SWINGS:
                stop=float(d[f'swing{n}'].iloc[green])*(1-base.SLIP); risk_pct=(entry-stop)/entry*100
                if not np.isfinite(stop) or stop<=0 or stop>=entry or risk_pct<.2 or risk_pct>20:continue
                rr,reason=base.simulate(path,entry,stop)
                if np.isfinite(rr):buckets[n].append({'swing':n,'market':m,'blue_time':bt,'green_time':idx[green],'entry_time':entry_time,'risk_pct':risk_pct,'result_r':rr,'exit_reason':reason})
            i=int(idx.searchsorted(entry_time+pd.Timedelta(minutes=base.HORIZON_MINUTES),side='left'))
    summaries=[]; alltr=[]
    for n in SWINGS:
        tr=pd.DataFrame(buckets[n])
        if not tr.empty:
            tr=tr.sort_values('entry_time').reset_index(drop=True); tr.to_csv(f'natural_swing{n}_compare_trades.csv',index=False); alltr.append(tr)
        summaries.append(summarize(tr,n))
    out=pd.DataFrame(summaries);out.to_csv('natural_swing_compare_summary.csv',index=False)
    if alltr:
        z=pd.concat(alltr,ignore_index=True);z['month']=pd.to_datetime(z.entry_time,utc=True).dt.to_period('M').astype(str)
        z.groupby(['swing','month']).agg(trades=('result_r','size'),avg_r=('result_r','mean'),sum_r=('result_r','sum'),win_rate_pct=('result_r',lambda x:(x>0).mean()*100)).reset_index().to_csv('natural_swing_compare_monthly.csv',index=False)
    print('\nSWING 5/10/20 FAIR COMPARISON\n',out.to_string(index=False),flush=True)
    print('Only stop lookback differs. Same signals, universe, fees/slippage, exits and validation period.',flush=True)

if __name__=='__main__':main()
