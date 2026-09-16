"""CatchWorld 1y Flow+pullback big-winner validation.
Uses the existing 5m path dataset. Future path is outcome-only, never an entry feature.
"""
from pathlib import Path
import pandas as pd
import numpy as np

DATA=Path('data/flow_path')
OUT=Path('results/big_winner'); OUT.mkdir(parents=True,exist_ok=True)
TARGETS=[3,5,8,10,15,20]
HORIZONS=[30,60,120,360]

def main():
    fs=sorted(DATA.glob('*.csv'))
    if not fs: raise FileNotFoundError('No Flow Path CSV shards found')
    d=pd.concat((pd.read_csv(f) for f in fs),ignore_index=True)
    d['entry_time']=pd.to_datetime(d['entry_time'],utc=True,errors='coerce')
    d=d.dropna(subset=['market','entry_time','offset_min','price'])
    entries=d[d.offset_min.eq(0)].copy()
    entries['kst_hour']=(entries.entry_time+pd.Timedelta(hours=9)).dt.hour
    print('DIAG entry_rows=',len(entries),'flow>=10=',int((entries.flow>=10).sum()),
          'ret30_range=',float(entries.ret30.min()),float(entries.ret30.max()),flush=True)
    # IMPORTANT: Flow Path stores ret30 as a decimal return (-0.025 == -2.5%), not percentage points.
    entries=entries[(entries.flow>=10)&entries.ret30.between(-0.025,-0.020)&entries.kst_hour.between(6,8)]
    print('DIAG selected_entries=',len(entries),flush=True)
    if entries.empty:
        raise RuntimeError('No candidates after filters; inspect DIAG values before changing thresholds')
    keys=set(zip(entries.market,entries.entry_time.astype(str)))
    d['_key']=list(zip(d.market,d.entry_time.astype(str)))
    d=d[d._key.isin(keys)].copy()
    rows=[]
    for (m,t),p in d.groupby(['market','entry_time'],sort=False):
        e=p[p.offset_min.eq(0)]
        if e.empty: continue
        ep=float(e.iloc[0].price); flow=float(e.iloc[0].flow); ret30=float(e.iloc[0].ret30)
        fut=p[(p.offset_min>0)&(p.offset_min<=360)].sort_values('offset_min')
        if fut.empty: continue
        r=(fut.price/ep-1)*100
        o={'market':m,'entry_time':t,'entry_price':ep,'flow':flow,'ret30':ret30,'mfe6h':float(r.max()),'mae6h':float(r.min())}
        for x in TARGETS:
            hit=fut.loc[r.ge(x),'offset_min']
            o[f'reach_{x}']=not hit.empty
            o[f'time_to_{x}_min']=np.nan if hit.empty else float(hit.iloc[0])
        for h in HORIZONS:
            z=fut[fut.offset_min<=h]
            rr=(z.price/ep-1)*100
            o[f'mfe_{h}m']=np.nan if z.empty else float(rr.max())
            o[f'mae_{h}m']=np.nan if z.empty else float(rr.min())
        rows.append(o)
    if not rows:
        raise RuntimeError('Candidates existed but no future paths were produced')
    ev=pd.DataFrame(rows).sort_values('entry_time')
    ev.to_csv(OUT/'events.csv',index=False)
    s={'events':len(ev),'mfe6h_mean':ev.mfe6h.mean(),'mae6h_mean':ev.mae6h.mean()}
    for x in TARGETS:
        s[f'reach_{x}_pct']=100*ev[f'reach_{x}'].mean()
        s[f'median_time_to_{x}_min']=ev[f'time_to_{x}_min'].median()
    pd.DataFrame([s]).to_csv(OUT/'summary.csv',index=False)
    print(pd.DataFrame([s]).to_string(index=False))

if __name__=='__main__': main()
