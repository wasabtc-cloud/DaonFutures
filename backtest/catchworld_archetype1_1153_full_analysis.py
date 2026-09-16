import glob,os
import numpy as np,pandas as pd
OUT='results/archetype1_1153_full';os.makedirs(OUT,exist_ok=True)
fs=glob.glob('strategy_b_input/**/*.csv',recursive=True);d=pd.concat([pd.read_csv(f) for f in fs],ignore_index=True)
d.time=pd.to_datetime(d.time,utc=True,errors='coerce');d=d.dropna(subset=['time']).drop_duplicates(['market','time']).sort_values(['market','time'])
feat=['turn_ratio','turn_accel_6_24','range24','range72','drawdown_30d','ret_6h','ret_12h','ret_24h','ret_72h','ret_168h','ret_336h','ret_720h']
for c in feat+['close','fwd_mfe_24h','fwd_mfe_72h'] : d[c]=pd.to_numeric(d[c],errors='coerce')
d['mfe24pct']=d.fwd_mfe_24h*100
# reproduce frozen 1414 pump episodes and K=3; cluster0 is 1153 broad archetype
cand=d[d.mfe24pct>=20].sort_values(['market','time']);ids=[];last={}
for i,r in cand.iterrows():
 if r.market not in last or (r.time-last[r.market]).total_seconds()>=72*3600:ids.append(i);last[r.market]=r.time
e=d.loc[ids,['market','time']+feat].copy();X=e[feat].replace([np.inf,-np.inf],np.nan);med=X.median();X=X.fillna(med);scale=(X.quantile(.75)-X.quantile(.25)).replace(0,1);Z=((X-med)/scale).clip(-8,8).to_numpy(float);rng=np.random.default_rng(42);C=Z[rng.choice(len(Z),3,replace=False)].copy()
for _ in range(80):
 ds=((Z[:,None,:]-C[None,:,:])**2).sum(2);lab=ds.argmin(1);N=np.vstack([Z[lab==j].mean(0) if np.any(lab==j) else C[j] for j in range(3)])
 if np.allclose(C,N,atol=1e-5):break
 C=N
e['cluster']=lab;t=e[e.cluster==0][['market','time']].rename(columns={'time':'anchor'});print('TARGET',len(t),'MARKETS',t.market.nunique())
by={m:g.set_index('time').sort_index() for m,g in d.groupby('market',sort=False)}
# timeline before/after pump anchor and exit lifecycle
snap=[];life=[]
for z in t.itertuples(index=False):
 g=by[z.market]
 for h in [-720,-336,-168,-72,-48,-24,-12,-6,-3,-1,0,1,3,6,12,24,48,72]:
  q=g.loc[g.index<=z.anchor+pd.Timedelta(hours=h)]
  if len(q):r=q.iloc[-1];snap.append({'market':z.market,'anchor':z.anchor,'h':h,**{c:r.get(c,np.nan) for c in feat},'close':r.close})
 w=g.loc[(g.index>=z.anchor)&(g.index<=z.anchor+pd.Timedelta(hours=72))]
 if len(w)>1:
  p0=float(w.close.iloc[0]);ret=w.close/p0-1;pt=ret.idxmax();peak=float(ret.max());rm=w.close.cummax();dd=w.close/rm-1
  first10=w.index[ret>=.10];reload=0
  if len(first10):
   a=first10[0];later=w.loc[w.index>=a+pd.Timedelta(hours=6)]
   if len(later) and (later.close/p0-1).max()>ret.loc[:a].max()+.03:reload=1
  life.append({'market':z.market,'anchor':z.anchor,'peak_ret':peak,'peak_h':(pt-z.anchor).total_seconds()/3600,'ret72':float(ret.iloc[-1]),'max_dd':float(dd.min()),'reload':reload})
s=pd.DataFrame(snap);s.to_csv(OUT+'/timeline.csv',index=False);lf=pd.DataFrame(life);lf.to_csv(OUT+'/lifecycle.csv',index=False)
# discover substructure INSIDE cluster0 from pre-anchor features only, K=2..8; silhouette sampled to control runtime
A=t.merge(d[['market','time']+feat],left_on=['market','anchor'],right_on=['market','time'],how='left');XX=A[feat].replace([np.inf,-np.inf],np.nan).fillna(med);ZZ=((XX-med)/scale).clip(-8,8).to_numpy(float)
def km(Z,k,seed=7):
 rg=np.random.default_rng(seed);cc=Z[rg.choice(len(Z),k,replace=False)].copy()
 for _ in range(100):
  di=((Z[:,None,:]-cc[None,:,:])**2).sum(2);la=di.argmin(1);nn=np.vstack([Z[la==j].mean(0) if np.any(la==j) else cc[j] for j in range(k)])
  if np.allclose(cc,nn,atol=1e-5):break
  cc=nn
 return la,cc
def sil(Z,la,maxn=1500):
 ix=np.arange(len(Z));
 if len(ix)>maxn:ix=np.random.default_rng(9).choice(ix,maxn,replace=False)
 vals=[]
 for i in ix:
  same=Z[la==la[i]];a=np.linalg.norm(same-Z[i],axis=1).mean() if len(same)>1 else 0;b=min(np.linalg.norm(Z[la==j]-Z[i],axis=1).mean() for j in np.unique(la) if j!=la[i]);vals.append((b-a)/max(a,b,1e-12))
 return np.mean(vals)
ks=[];best=None
for k in range(2,9):
 la,cc=km(ZZ,k);sc=sil(ZZ,la);ks.append({'k':k,'silhouette':sc});
 if best is None or sc>best[0]:best=(sc,k,la)
pd.DataFrame(ks).to_csv(OUT+'/subcluster_k.csv',index=False);A['subcluster']=best[2];A.to_csv(OUT+'/events_with_subcluster.csv',index=False)
prof=A.groupby('subcluster').agg(events=('market','size'),markets=('market','nunique'),**{c:(c,'median') for c in feat}).reset_index();prof.to_csv(OUT+'/subcluster_profiles.csv',index=False)
# timeline group medians + lifecycle summary
sm=s.groupby('h').agg(events=('market','size'),markets=('market','nunique'),turn_ratio=('turn_ratio','median'),accel=('turn_accel_6_24','median'),range24=('range24','median'),ret24=('ret_24h','median'),ret72=('ret_72h','median')).reset_index();sm.to_csv(OUT+'/timeline_summary.csv',index=False)
summary={'events':len(lf),'peak_ret_median':lf.peak_ret.median(),'peak_h_median':lf.peak_h.median(),'peak_h_q25':lf.peak_h.quantile(.25),'peak_h_q75':lf.peak_h.quantile(.75),'ret72_median':lf.ret72.median(),'reload_rate':lf.reload.mean(),'best_subcluster_k':best[1],'best_silhouette':best[0]};pd.DataFrame([summary]).to_csv(OUT+'/summary.csv',index=False);print(pd.DataFrame([summary]).to_string(index=False));print(pd.DataFrame(ks).to_string(index=False));print(prof.to_string(index=False))
