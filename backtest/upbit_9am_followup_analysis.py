"""Follow-up statistical analysis for 09:00 KST research outputs.
This script analyzes historical samples only and does not place orders.
"""
from pathlib import Path
import numpy as np
import pandas as pd

OUT=Path('results_9am')
FEATURES=['pre_ret_5m','pre_ret_15m','pre_ret_30m','value5_ratio','value30_ratio','value_accel5','pre_breakout_30m']


def main():
    df=pd.read_csv(OUT/'upbit_9am_samples.csv')
    top5=(df.sort_values(['day_kst','post_max_60m'],ascending=[True,False])
            .groupby('day_kst').head(5).copy())
    keys=set(zip(top5.day_kst,top5.market))
    df['is_top5']=[int((d,m) in keys) for d,m in zip(df.day_kst,df.market)]

    contrast=[]
    for f in FEATURES:
        a=df[df.is_top5==1][f].dropna(); b=df[df.is_top5==0][f].dropna()
        contrast.append({'feature':f,'top5_mean':a.mean(),'other_mean':b.mean(),
                         'top5_median':a.median(),'other_median':b.median(),
                         'median_diff':a.median()-b.median(),'top5_n':len(a),'other_n':len(b)})
    pd.DataFrame(contrast).to_csv(OUT/'upbit_9am_top5_vs_others.csv',index=False)

    top5['rank_9am']=top5.groupby('day_kst')['post_max_60m'].rank(method='first',ascending=False).astype(int)
    rows=[]
    for label,sub in [('TOP1',top5[top5.rank_9am==1]),('TOP2',top5[top5.rank_9am<=2]),('TOP5',top5)]:
        r={'group':label,'samples':len(sub),'avg_max_return':sub.post_max_60m.mean()}
        for f in FEATURES:r[f]=sub[f].mean()
        rows.append(r)
    for pct in [5,10,15,20]:
        sub=df[df[f'label_{pct}pct']==1]
        r={'group':f'>={pct}%','samples':len(sub),'avg_max_return':sub.post_max_60m.mean()}
        for f in FEATURES:r[f]=sub[f].mean()
        rows.append(r)
    pd.DataFrame(rows).to_csv(OUT/'upbit_9am_rank_threshold_profiles.csv',index=False)

    # Chronological holdout: first 2/3 for discovery, last 1/3 untouched for validation.
    dates=sorted(df.day_kst.unique()); cut=max(1,int(len(dates)*2/3))
    train_dates=set(dates[:cut]); test_dates=set(dates[cut:])
    train=df[df.day_kst.isin(train_dates)].copy(); test=df[df.day_kst.isin(test_dates)].copy()

    # Transparent score built only from pre-09:00 fields.
    for data in (train,test):
        data['validation_score']=(np.log1p(data.value5_ratio.clip(lower=0))*1.2+
                                  np.log1p(data.value30_ratio.clip(lower=0))*1.0+
                                  np.log1p(data.value_accel5.clip(lower=0))*1.0-
                                  data.pre_ret_30m.clip(lower=0)*8)

    def metrics(data,split):
        actual=(data.sort_values(['day_kst','post_max_60m'],ascending=[True,False]).groupby('day_kst').head(5)
                  .groupby('day_kst').market.apply(set).to_dict())
        out=[]
        for k in [1,3,5]:
            pred=data.sort_values(['day_kst','validation_score'],ascending=[True,False]).groupby('day_kst').head(k)
            overlaps=[]
            for d,g in pred.groupby('day_kst'):
                overlaps.append(len(set(g.market)&actual.get(d,set))/k)
            out.append({'split':split,'topk':k,'days':pred.day_kst.nunique(),
                        'realized_top5_overlap_pct':np.mean(overlaps)*100 if overlaps else np.nan,
                        'hit_5pct':pred.label_5pct.mean()*100,
                        'hit_10pct':pred.label_10pct.mean()*100,
                        'hit_15pct':pred.label_15pct.mean()*100,
                        'hit_20pct':pred.label_20pct.mean()*100})
        return out

    pd.DataFrame(metrics(train,'train')+metrics(test,'test')).to_csv(OUT/'upbit_9am_oos_prediction_metrics.csv',index=False)
    pd.DataFrame([{'train_start':min(train_dates),'train_end':max(train_dates),
                   'test_start':min(test_dates),'test_end':max(test_dates),
                   'train_days':len(train_dates),'test_days':len(test_dates)}]).to_csv(OUT/'upbit_9am_oos_split.csv',index=False)

    candidates=test.sort_values(['day_kst','validation_score'],ascending=[True,False]).groupby('day_kst').head(5).copy()
    candidates.to_csv(OUT/'upbit_9am_holdout_top5_candidates.csv',index=False)
    print('9AM follow-up analysis complete',flush=True)

if __name__=='__main__':main()
