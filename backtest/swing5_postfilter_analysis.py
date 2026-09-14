import pandas as pd
import numpy as np

INPUT='natural_swing5_trades.csv'
OUT='swing5_postfilter_comparison.csv'

DELAY_RANGES=[(1,5),(2,5),(3,5),(3,8),(4,8),(4,12),(5,12),(8,20)]
RISK_RANGES=[(.2,20),(.3,10),(.5,8),(1,8),(.5,5),(1,5)]


def metrics(df):
    if df.empty:return None
    r=df.result_r.astype(float)
    gp=r[r>0].sum(); gl=-r[r<0].sum(); pf=gp/gl if gl>0 else np.inf
    eq=100.0; peak=100.0; mdd=0.0
    for x in r:
        eq*=max(0.0,1.0+0.01*float(x)); peak=max(peak,eq); mdd=max(mdd,(peak-eq)/peak)
    return dict(n=len(df),avg_r=r.mean(),win_rate=(r>0).mean()*100,pf=pf,mdd=mdd*100,ending_equity=eq)


def main():
    tr=pd.read_csv(INPUT)
    for c in ['blue_time','green_time','entry_time']:
        tr[c]=pd.to_datetime(tr[c],utc=True)
    tr['delay_min']=(tr.green_time-tr.blue_time).dt.total_seconds()/60
    tr=tr.sort_values('entry_time').reset_index(drop=True)
    cut=len(tr)//2
    first=tr.iloc[:cut].copy(); second=tr.iloc[cut:].copy()
    rows=[]
    for dmin,dmax in DELAY_RANGES:
        for rmin,rmax in RISK_RANGES:
            def filt(x):
                return x[(x.delay_min>=dmin)&(x.delay_min<=dmax)&(x.risk_pct>=rmin)&(x.risk_pct<=rmax)]
            a,b=filt(first),filt(second); ma,mb=metrics(a),metrics(b)
            if not ma or not mb:continue
            row={'delay_min':dmin,'delay_max':dmax,'risk_min':rmin,'risk_max':rmax}
            row.update({'first_'+k:v for k,v in ma.items()}); row.update({'second_'+k:v for k,v in mb.items()})
            row['passes_basic_robustness']=(ma['n']>=15 and mb['n']>=15 and ma['pf']>=1.0 and mb['pf']>=1.0)
            rows.append(row)
    out=pd.DataFrame(rows).sort_values(['passes_basic_robustness','second_pf','first_pf'],ascending=[False,False,False])
    out.to_csv(OUT,index=False)
    print(out.to_string(index=False))
    print('\nNo filter is considered live-ready from this post-filter test alone; raw-feature walk-forward validation is still required.')

if __name__=='__main__':main()
