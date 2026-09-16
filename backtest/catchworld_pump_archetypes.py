import glob,os
import numpy as np,pandas as pd
OUT='results/pump_archetypes';os.makedirs(OUT,exist_ok=True)
fs=glob.glob('strategy_b_input/**/*.csv',recursive=True);d=pd.concat([pd.read_csv(f) for f in fs],ignore_index=True)
d.time=pd.to_datetime(d.time,utc=True,errors='coerce');d=d.dropna(subset=['time']).drop_duplicates(['market','time']).sort_values(['market','time'])
feat=['turn_ratio','turn_accel_6_24','range24','range72','drawdown_30d','ret_6h','ret_12h','ret_24h','ret_72h','ret_168h','ret_336h','ret_720h']
for c in feat+['fwd_mfe_24h','fwd_mfe_72h']:d[c]=pd.to_numeric(d[c],errors='coerce')
# source future returns are decimal; labels only, never clustering inputs
for c in ['fwd_mfe_24h','fwd_mfe_72h']: d[c]=d[c]*100
# independent pump episodes: first >=20% label per market after 72h cooldown
cand=d[d.fwd_mfe_24h>=20].sort_values(['market','time']);ids=[];last={}
for i,r in cand.iterrows():
 if r.market not in last or (r.time-last[r.market]).total_seconds()>=72*3600:ids.append(i);last[r.market]=r.time
e=d.loc[ids,['market','time']+feat+['fwd_mfe_24h','fwd_mfe_72h']].copy()
# robust standardization across pump events; unsupervised kmeans implemented locally, choose k by silhouette sample
X=e[feat].replace([np.inf,-np.inf],np.nan);med=X.median();X=X.fillna(med);q1=X.quantile(.25);q3=X.quantile(.75);scale=(q3-q1).replace(0,1);Z=((X-med)/scale).clip(-8,8).to_numpy(float)
rng=np.random.default_rng(42)
def km(Z,k,it=80):
 C=Z[rng.choice(len(Z),k,replace=False)].copy()
 for _ in range(it):
  ds=((Z[:,None,:]-C[None,:,:])**2).sum(2);lab=ds.argmin(1);N=np.vstack([Z[lab==j].mean(0) if np.any(lab==j) else C[j] for j in range(k)])
  if np.allclose(C,N,atol=1e-5):break
  C=N
 return lab,C
def sil(Z,lab,maxn=1800):
 ix=np.arange(len(Z));
 if len(ix)>maxn:ix=rng.choice(ix,maxn,replace=False)
 A=Z[ix];L=lab[ix];D=np.sqrt(((A[:,None,:]-A[None,:,:])**2).sum(2));vals=[]
 for i in range(len(ix)):
  same=L==L[i];same[i]=False;a=D[i,same].mean() if same.any() else 0
  bs=[D[i,L==j].mean() for j in np.unique(L) if j!=L[i] and np.any(L==j)];b=min(bs) if bs else 0
  vals.append((b-a)/max(a,b,1e-9))
 return float(np.mean(vals))
rows=[];models={}
for k in range(3,13):
 lab,C=km(Z,k);s=sil(Z,lab);rows.append({'k':k,'silhouette':s});models[k]=(lab,C)
sc=pd.DataFrame(rows);best=int(sc.sort_values('silhouette',ascending=False).iloc[0].k);lab,C=models[best];e['cluster']=lab
# cluster profiles + human-readable dominant deviations
prof=[]
for j,g in e.groupby('cluster'):
 r={'cluster':j,'events':len(g),'markets':g.market.nunique(),'median_mfe24':g.fwd_mfe_24h.median(),'p50plus':(g.fwd_mfe_24h>=50).mean(),'p100plus':(g.fwd_mfe_24h>=100).mean()}
 for c in feat:r[c]=g[c].median()
 prof.append(r)
p=pd.DataFrame(prof).sort_values('events',ascending=False)
# controls: same markets/hours excluding +/-96h around pump starts, summarize cluster distinguishing z-centers
cent=pd.DataFrame(C,columns=feat);names=[]
for j in range(best):
 top=cent.loc[j].abs().sort_values(ascending=False).head(5).index
 names.append(' | '.join([f'{c}:{cent.loc[j,c]:+.2f}' for c in top]))
p=p.merge(pd.DataFrame({'cluster':range(best),'dominant_features':names}),on='cluster',how='left')
sc.to_csv(OUT+'/k_selection.csv',index=False);e.to_csv(OUT+'/pump_events_clustered.csv',index=False);p.to_csv(OUT+'/archetype_profiles.csv',index=False)
print('PUMP EPISODES',len(e),'MARKETS',e.market.nunique(),'BEST_K',best);print(sc.to_string(index=False));print('\nARCHETYPES\n',p.to_string(index=False))
