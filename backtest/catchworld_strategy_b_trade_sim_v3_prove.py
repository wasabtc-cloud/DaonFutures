import glob,os
import numpy as np,pandas as pd
OUT='results/strategy_b_trade_sim_v3_prove';os.makedirs(OUT,exist_ok=True)
FEE=.0005;START=1_000_000.0
fs=glob.glob('strategy_b_input/**/*.csv',recursive=True);d=pd.concat([pd.read_csv(f) for f in fs],ignore_index=True)
d.time=pd.to_datetime(d.time,utc=True,errors='coerce');d=d.dropna(subset=['time']).drop_duplicates(['market','time']).sort_values(['market','time'])
cols=['close','turn_ratio','turn_accel_6_24','ret_6h','ret_12h','ret_24h','ret_72h','ret_168h','range24','range72','drawdown_30d']
for c in cols:
 if c in d:d[c]=pd.to_numeric(d[c],errors='coerce')
# WATCH -> READY -> IGNITION -> BUY. V3 adds post-entry PROVE at 3-6h.
sigs=[]
for m,g in d.groupby('market',sort=False):
 g=g.set_index('time').sort_index();base=((g.turn_ratio>=4)&(g.ret_24h<.10)).astype(int);watch=base.rolling('48h',min_periods=1).sum()>=3;cool=None
 for j in np.flatnonzero(watch.to_numpy()):
  wt=g.index[j]
  if cool is not None and wt<cool:continue
  r0=g.iloc[j];p0=float(r0.close);reversal=(r0.drawdown_30d<=-.22)&(r0.ret_168h<=0);trend=(r0.drawdown_30d>-.22)&(r0.ret_72h>0)&(r0.ret_24h>-.02)
  if not(reversal or trend):continue
  setup='REVERSAL' if reversal else 'TREND';w=g.loc[(g.index>wt)&(g.index<=wt+pd.Timedelta(hours=12))]
  if len(w)<3:continue
  med3=w.turn_ratio.rolling(3,min_periods=2).median();pr=w.close/p0-1
  if setup=='REVERSAL':cond=(w.turn_ratio>=2.5)&(med3>=2)&(w.turn_accel_6_24>=.8)&(pr>=.02)&(pr<.10)&(w.ret_6h>0)
  else:cond=(w.turn_ratio>=2)&(med3>=1.8)&(w.turn_accel_6_24>=.8)&(pr>=.01)&(pr<.08)&(w.ret_6h>0)&(w.ret_24h>0)
  hit=w.index[cond.fillna(False)]
  if len(hit):bt=hit[0];sigs.append((bt,m,wt,setup));cool=bt+pd.Timedelta(hours=72)
s=pd.DataFrame(sigs,columns=['buy_time','market','watch_time','setup']).sort_values('buy_time');print('BUY_SIGNALS',len(s))
by={m:g.set_index('time').sort_index() for m,g in d.groupby('market',sort=False)}
equity=START;busy=pd.Timestamp.min.tz_localize('UTC');tr=[]
for z in s.itertuples(index=False):
 if z.buy_time<=busy:continue
 g=by[z.market];w=g.loc[(g.index>=z.buy_time)&(g.index<=z.buy_time+pd.Timedelta(hours=72))]
 if len(w)<2:continue
 entry=float(w.close.iloc[0]);peak=entry;exit_t=w.index[-1];exit_p=float(w.close.iloc[-1]);reason='TIME72';proved=False
 # PROVE window: by hour 6 require sustained flow + defended price + positive short structure.
 provew=w.loc[(w.index>=z.buy_time+pd.Timedelta(hours=3))&(w.index<=z.buy_time+pd.Timedelta(hours=6))]
 prove_t=None
 for t,r in provew.iterrows():
  recent=w.loc[(w.index>=z.buy_time)&(w.index<=t)].tail(3);flow_med=recent.turn_ratio.median();price_ok=float(r.close)>=entry*.995;structure=(r.ret_6h>0) or (float(r.close)>=recent.close.min()*1.01)
  if flow_med>=1.8 and r.turn_ratio>=1.5 and price_ok and structure:proved=True;prove_t=t;break
 # If BUY fails to prove itself by 6h, leave immediately at first available >=6h close.
 if not proved:
  q=w.loc[w.index>=z.buy_time+pd.Timedelta(hours=6)]
  if len(q):exit_t=q.index[0];exit_p=float(q.close.iloc[0]);reason='FAIL_PROVE6'
 else:
  weakst=0
  for t,r in w.loc[w.index>prove_t].iterrows():
   p=float(r.close);peak=max(peak,p);ret=p/entry-1;dd=p/peak-1;weak=((r.turn_ratio<1.2)or(r.turn_accel_6_24<.75))and(r.ret_6h<0);weakst=weakst+1 if weak else 0
   if ret<=-.07:exit_t=t;exit_p=p;reason='HARD7';break
   if (t-z.buy_time)>=pd.Timedelta(hours=12) and peak/entry-1<.04 and weakst>=3:exit_t=t;exit_p=p;reason='DEAD12';break
   if peak/entry-1>=.10 and dd<=-.08 and weakst>=2:exit_t=t;exit_p=p;reason='FLOW_DD8';break
   if (t-z.buy_time)>=pd.Timedelta(hours=36) and peak/entry-1<.10 and ret<0 and weakst>=2:exit_t=t;exit_p=p;reason='WEAK36';break
 net=(exit_p/entry)*(1-FEE)/(1+FEE);before=equity;equity*=net;tr.append({'market':z.market,'setup':z.setup,'proved':proved,'watch_time':z.watch_time,'buy_time':z.buy_time,'sell_time':exit_t,'entry':entry,'exit':exit_p,'net_ret':net-1,'hold_h':(exit_t-z.buy_time).total_seconds()/3600,'reason':reason,'equity_before':before,'equity_after':equity});busy=exit_t
r=pd.DataFrame(tr);r.to_csv(OUT+'/trades.csv',index=False)
if len(r):
 eq=np.r_[START,r.equity_after];run=np.maximum.accumulate(eq);mdd=np.min(eq/run-1);gp=r.loc[r.net_ret>0,'net_ret'].sum();gl=-r.loc[r.net_ret<0,'net_ret'].sum();pf=gp/gl if gl>0 else np.inf
 summary={'start_krw':START,'final_krw':equity,'multiple':equity/START,'trades':len(r),'win_rate':(r.net_ret>0).mean(),'avg_net_ret':r.net_ret.mean(),'median_net_ret':r.net_ret.median(),'pf':pf,'mdd':mdd,'avg_hold_h':r.hold_h.mean(),'proved':r.proved.sum(),'failed_prove':(~r.proved).sum(),**{x:int((r.reason==x).sum()) for x in ['FAIL_PROVE6','HARD7','DEAD12','FLOW_DD8','WEAK36','TIME72']}}
else:summary={'start_krw':START,'final_krw':START,'multiple':1,'trades':0}
pd.DataFrame([summary]).to_csv(OUT+'/summary.csv',index=False);print(pd.DataFrame([summary]).to_string(index=False));print(r.groupby(['proved','reason']).net_ret.agg(['count','mean','median']).to_string() if len(r) else '')
