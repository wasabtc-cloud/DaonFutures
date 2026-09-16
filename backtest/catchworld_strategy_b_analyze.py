import glob, os
import numpy as np
import pandas as pd

IN='strategy_b_input'
OUT='results/strategy_b_analysis'
os.makedirs(OUT,exist_ok=True)
files=glob.glob(f'{IN}/**/*.csv',recursive=True)
print('FILES',len(files))
parts=[]
for f in files:
    try:
        d=pd.read_csv(f)
        if len(d): parts.append(d)
    except Exception as e: print('SKIP',f,e)
if not parts: raise RuntimeError('no csv input')
df=pd.concat(parts,ignore_index=True)
print('ROWS',len(df),'COLS',list(df.columns))
# normalize likely names
if 'time' not in df and 'timestamp' in df: df=df.rename(columns={'timestamp':'time'})
if 'market' not in df: raise RuntimeError('market missing')
# expected scout labels/features are retained; discover future-max columns dynamically
future=[c for c in df.columns if ('future' in c.lower() or 'mfe' in c.lower()) and pd.api.types.is_numeric_dtype(df[c]]
# fallback known scout names
for c in ['future_max_6h','future_max_12h','future_max_24h','future_max_48h','future_max_72h']:
    if c in df and c not in future: future.append(c)
print('FUTURE',future)
if not future: raise RuntimeError('no future outcome column')
# choose 24h if possible, else longest-looking outcome
fcol=next((c for c in future if '24' in c),future[-1])
y=pd.to_numeric(df[fcol],errors='coerce')
# normalize decimal vs percent
scale=100.0 if y.abs().quantile(.95)<5 else 1.0
y_pct=y*scale
df['_future_pct']=y_pct
# de-duplicate overlapping pump labels: keep earliest event per market within 24h when >=20
sortcols=['market']+(['time'] if 'time' in df else [])
df=df.sort_values(sortcols)
pump=df[df._future_pct>=20].copy()
if 'time' in pump:
    pump['time']=pd.to_datetime(pump.time,utc=True,errors='coerce')
    keep=[]; last={}
    for i,r in pump.iterrows():
        t=r.time; m=r.market
        if pd.isna(t) or m not in last or (t-last[m]).total_seconds()>=86400:
            keep.append(i); last[m]=t
    events=pump.loc[keep].copy()
else: events=pump
thresholds=[]
for th in [20,30,50,100]: thresholds.append({'threshold_pct':th,'events':int((events._future_pct>=th).sum()),'markets':int(events.loc[events._future_pct>=th,'market'].nunique())})
pd.DataFrame(thresholds).to_csv(f'{OUT}/event_counts.csv',index=False)
# compare pre-known numeric features; exclude future/outcome/leakage columns
exclude=set(future+['_future_pct'])
nums=[c for c in df.select_dtypes(include=np.number).columns if c not in exclude and not any(x in c.lower() for x in ['future','mfe','mae','target','label','reach'])]
rows=[]
pos=df._future_pct>=20
for c in nums:
    a=pd.to_numeric(df.loc[pos,c],errors='coerce').replace([np.inf,-np.inf],np.nan).dropna()
    b=pd.to_numeric(df.loc[~pos,c],errors='coerce').replace([np.inf,-np.inf],np.nan).dropna()
    if len(a)<20 or len(b)<20: continue
    am,bm=a.median(),b.median(); pooled=np.nanstd(pd.concat([a,b]).values)
    rows.append({'feature':c,'pump_median':am,'control_median':bm,'median_diff':am-bm,'std_effect':(a.mean()-b.mean())/pooled if pooled>0 else np.nan,'pump_n':len(a),'control_n':len(b)})
cmp=pd.DataFrame(rows)
if len(cmp): cmp=cmp.reindex(cmp.std_effect.abs().sort_values(ascending=False).index)
cmp.to_csv(f'{OUT}/feature_compare_20.csv',index=False)
# top event examples
cols=['market']+(['time'] if 'time' in events else [])+['_future_pct']+nums[:30]
events.sort_values('_future_pct',ascending=False)[cols].head(500).to_csv(f'{OUT}/top_events.csv',index=False)
print(pd.DataFrame(thresholds).to_string(index=False))
print('TOP FEATURES')
print(cmp.head(25).to_string(index=False) if len(cmp) else 'none')
