"""Discover causal pre-pump sequences in scout data.
Compares 1,414 pump anchors against matched controls without imposing the old 4 archetypes.
Future MFE is label/anchor construction only. Features are prior/current observations.
"""
from pathlib import Path
import glob, pandas as pd, numpy as np

IN='strategy_b_input'; OUT=Path('results/prepump_sequence'); OUT.mkdir(parents=True,exist_ok=True)
files=glob.glob(f'{IN}/**/*.csv',recursive=True); dfs=[]
for f in files:
    try:
        d=pd.read_csv(f)
        if {'market','time','fwd_mfe_24h'}.issubset(d.columns): dfs.append(d)
    except Exception: pass
x=pd.concat(dfs,ignore_index=True).drop_duplicates(['market','time']); x['time']=pd.to_datetime(x.time,utc=True); x=x.sort_values(['market','time'])
num=['turnover','turn_ratio','turn_accel_6_24','range24','range72','drawdown_30d','ret_6h','ret_12h','ret_24h','ret_72h','ret_168h','ret_336h','ret_720h','fwd_mfe_24h','fwd_mfe_72h']
for c in num:
    if c in x:x[c]=pd.to_numeric(x[c],errors='coerce')
# anchors: first >=20% next-24h event, 72h cooldown
anchors=[]
for m,g in x.groupby('market'):
    last=None
    for _,r in g[g.fwd_mfe_24h>=.20].iterrows():
        if last is None or (r.time-last).total_seconds()>=72*3600: anchors.append((m,r.time)); last=r.time
# controls same market, <20% next72h and >=96h from anchors, deterministic up to 3/anchor
byA={}
for m,t in anchors:byA.setdefault(m,[]).append(t)
controls=[]
for m,g in x.groupby('market'):
    aa=byA.get(m,[]); cand=g[g.fwd_mfe_72h<.20]
    if aa: cand=cand[cand.time.map(lambda t:min(abs((t-a).total_seconds()) for a in aa)>=96*3600)]
    n=3*len(aa)
    if n and len(cand): controls += [(m,t) for t in cand.time.iloc[np.linspace(0,len(cand)-1,min(n,len(cand)),dtype=int)]]
LOOK=[168,72,24,12,6,3,1,0]
features=['turn_ratio','turn_accel_6_24','turnover','range24','range72','drawdown_30d','ret_6h','ret_12h','ret_24h','ret_72h']
idx={(m):g.set_index('time').sort_index() for m,g in x.groupby('market')}
def snapshots(events,label):
    rows=[]
    for eid,(m,t) in enumerate(events):
        g=idx[m]
        for h in LOOK:
            target=t-pd.Timedelta(hours=h); q=g.loc[:target]
            if q.empty:continue
            r=q.iloc[-1]; z={'label':label,'event_id':eid,'market':m,'anchor':t,'lookback_h':h}
            for c in features:z[c]=r.get(c,np.nan)
            rows.append(z)
    return rows
s=pd.DataFrame(snapshots(anchors,'PUMP')+snapshots(controls,'CONTROL')); s.to_csv(OUT/'sequence_snapshots.csv',index=False)
# Transitions between adjacent lookbacks. This asks what CHANGED, not just absolute levels.
wide=s.pivot_table(index=['label','event_id','market','anchor'],columns='lookback_h',values=features,aggfunc='last')
trs=[]
for ix,r in wide.iterrows():
    label,eid,m,a=ix
    for old,new in zip(LOOK[:-1],LOOK[1:]):
        z={'label':label,'event_id':eid,'market':m,'anchor':a,'from_h':old,'to_h':new}
        for c in features:
            try:z[c+'_change']=r[(c,new)]-r[(c,old)]
            except:z[c+'_change']=np.nan
        trs.append(z)
t=pd.DataFrame(trs); t.to_csv(OUT/'sequence_transitions.csv',index=False)
# Descriptive separation table: medians and standardized median gap, no fitted thresholds.
summary=[]
for h in LOOK:
    a=s[(s.label=='PUMP')&(s.lookback_h==h)]; b=s[(s.label=='CONTROL')&(s.lookback_h==h)]
    for c in features:
        ap=a[c].dropna(); bp=b[c].dropna()
        if len(ap)<20 or len(bp)<20:continue
        pooled=pd.concat([ap,bp]); scale=pooled.quantile(.75)-pooled.quantile(.25)
        summary.append({'lookback_h':h,'feature':c,'pump_median':ap.median(),'control_median':bp.median(),'median_gap':ap.median()-bp.median(),'gap_over_iqr':(ap.median()-bp.median())/scale if scale else np.nan,'pump_n':len(ap),'control_n':len(bp)})
pd.DataFrame(summary).sort_values('gap_over_iqr',key=lambda q:q.abs(),ascending=False).to_csv(OUT/'feature_separation.csv',index=False)
print('PUMP',len(anchors),'CONTROL',len(controls),'SNAPSHOTS',len(s),'TRANSITIONS',len(t))
print(pd.DataFrame(summary).sort_values('gap_over_iqr',key=lambda q:q.abs(),ascending=False).head(25).to_string(index=False))
