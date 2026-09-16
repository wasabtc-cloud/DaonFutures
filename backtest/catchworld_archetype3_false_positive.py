import glob,os
import numpy as np,pandas as pd
OUT='results/archetype3_false_positive';os.makedirs(OUT,exist_ok=True)
fs=glob.glob('strategy_b_input/**/*.csv',recursive=True);d=pd.concat([pd.read_csv(f) for f in fs],ignore_index=True)
d.time=pd.to_datetime(d.time,utc=True,errors='coerce');d=d.dropna(subset=['time']).drop_duplicates(['market','time']).sort_values(['market','time'])
num=['turn_ratio','turn_accel_6_24','ret_24h','fwd_mfe_24h','fwd_mfe_72h','range24','range72','drawdown_30d','ret_6h','ret_12h','ret_72h','ret_168h','ret_336h','ret_720h']
for c in num:d[c]=pd.to_numeric(d[c],errors='coerce')
d['mfe24pct']=d.fwd_mfe_24h*100;d['mfe72pct']=d.fwd_mfe_72h*100
feat=['turn_ratio','turn_accel_6_24','range24','range72','drawdown_30d','ret_6h','ret_12h','ret_24h','ret_72h','ret_168h','ret_336h','ret_720h']
# reproduce target cluster exactly as prior persistence run
cand=d[d.mfe24pct>=20].sort_values(['market','time']);ids=[];last={}
for i,r in cand.iterrows():
 if r.market not in last or (r.time-last[r.market]).total_seconds()>=72*3600:ids.append(i);last[r.market]=r.time
e=d.loc[ids,['market','time']+feat].copy();X=e[feat].replace([np.inf,-np.inf],np.nan);med=X.median();X=X.fillna(med);scale=(X.quantile(.75)-X.quantile(.25)).replace(0,1);Z=((X-med)/scale).clip(-8,8).to_numpy(float);rng=np.random.default_rng(42);C=Z[rng.choice(len(Z),3,replace=False)].copy()
for _ in range(80):
 ds=((Z[:,None,:]-C[None,:,:])**2).sum(2);lab=ds.argmin(1);N=np.vstack([Z[lab==j].mean(0) if np.any(lab==j) else C[j] for j in range(3)])
 if np.allclose(C,N,atol=1e-5):break
 C=N
e['cluster']=lab;target=e[e.cluster==2][['market','time']].rename(columns={'time':'anchor'})
print('TARGET',len(target))
# Cache markets once. Controls: same market, same broad calendar history, no +20% in next 72h,
# at least 96h away from any known >=20% pump anchor. Sample up to 5 controls per positive event near its date.
by={m:g.set_index('time').sort_index() for m,g in d.groupby('market',sort=False)}
pump_times={m:np.array(g.time.values,dtype='datetime64[ns]') for m,g in e.groupby('market')}
controls=[]
for ev in target.itertuples(index=False):
 g=by[ev.market]; lo=ev.anchor-pd.Timedelta(days=45);hi=ev.anchor+pd.Timedelta(days=45)
 c=g.loc[(g.index>=lo)&(g.index<=hi)&(g.mfe72pct<20)&g.turn_ratio.notna()].copy()
 if c.empty:continue
 pts=pump_times.get(ev.market,np.array([],dtype='datetime64[ns]'))
 if len(pts):
  tt=c.index.values.astype('datetime64[ns]');dist=np.min(np.abs(tt[:,None]-pts[None,:]),axis=1)/np.timedelta64(1,'h');c=c.iloc[np.where(dist>=96)[0]]
 # deterministic, spread through time, max five per event
 if len(c)>5:
  ix=np.linspace(0,len(c)-1,5).round().astype(int);c=c.iloc[ix]
 for t in c.index:controls.append((ev.market,t))
controls=pd.DataFrame(controls,columns=['market','anchor']).drop_duplicates()
print('CONTROLS',len(controls),'MARKETS',controls.market.nunique())

def first_signal(m,t,tr,hits,span):
 g=by[m].loc[(by[m].index>=t-pd.Timedelta(hours=48))&(by[m].index<t),['turn_ratio','turn_accel_6_24','ret_24h']]
 if g.empty:return None
 hit=((g.turn_ratio>=tr)&(g.ret_24h<.10)).astype('int8');acc=(g.turn_accel_6_24>=1).astype('int8')
 ok=(hit.rolling(f'{span}h',min_periods=1).sum()>=hits)&(acc.rolling(f'{span}h',min_periods=1).sum()>=1)
 if not ok.any():return None
 return ok.index[np.flatnonzero(ok.to_numpy())[0]]
# Freeze the three simple rules already examined; do not search new thresholds on controls.
rules=[(2,3,48),(3,3,48),(4,3,48)]
rows=[];details=[]
for tr,hits,span in rules:
 pos=0;plead=[]
 for ev in target.itertuples(index=False):
  s=first_signal(ev.market,ev.anchor,tr,hits,span)
  if s is not None:pos+=1;plead.append((ev.anchor-s).total_seconds()/3600)
 neg=0
 for ev in controls.itertuples(index=False):
  s=first_signal(ev.market,ev.anchor,tr,hits,span)
  if s is not None:neg+=1;details.append({'rule':f'{tr}x{hits}','market':ev.market,'anchor':ev.anchor,'signal':s,'control':1})
 recall=pos/len(target);fpr=neg/len(controls) if len(controls) else np.nan
 # matched-sample PPV is descriptive only because control sampling changes prevalence.
 ppv=pos/(pos+neg) if pos+neg else np.nan
 rows.append({'turn_ratio_min':tr,'min_hits':hits,'window_hours':span,'positive_caught':pos,'positive_total':len(target),'recall':recall,'controls_flagged':neg,'controls_total':len(controls),'control_fpr':fpr,'matched_ppv':ppv,'median_positive_lead_h':np.median(plead) if plead else np.nan,'lift_vs_control_fpr':recall/fpr if fpr>0 else np.nan})
pd.DataFrame(rows).to_csv(OUT+'/false_positive_summary.csv',index=False);controls.to_csv(OUT+'/matched_controls.csv',index=False);pd.DataFrame(details).to_csv(OUT+'/flagged_controls.csv',index=False)
print(pd.DataFrame(rows).to_string(index=False))
