import glob,os
import numpy as np,pandas as pd
OUT='results/strategy_b_trade_sim_v1';os.makedirs(OUT,exist_ok=True)
FEE=.0005; START=1_000_000.0
fs=glob.glob('strategy_b_input/**/*.csv',recursive=True);d=pd.concat([pd.read_csv(f) for f in fs],ignore_index=True)
d.time=pd.to_datetime(d.time,utc=True,errors='coerce');d=d.dropna(subset=['time']).drop_duplicates(['market','time']).sort_values(['market','time'])
for c in ['close','turn_ratio','turn_accel_6_24','ret_24h','range24'] : d[c]=pd.to_numeric(d[c],errors='coerce')
# Causal hourly approximation of current lifecycle: WATCH=4x flow persistence, READY=flow survives, BUY=price ignition.
# No future labels are used for entry/exit. One account, one open position, all-in compounding.
sigs=[]
for m,g in d.groupby('market',sort=False):
 g=g.set_index('time').sort_index(); base=((g.turn_ratio>=4)&(g.ret_24h<.10)).astype(int)
 watch=base.rolling('48h',min_periods=1).sum()>=3
 # confirmation uses only information observed after WATCH: persistent capital + positive price expansion
 idx=np.flatnonzero(watch.to_numpy())
 cooldown=None
 for j in idx:
  t=g.index[j]
  if cooldown is not None and t<cooldown: continue
  w=g.loc[(g.index>=t)&(g.index<=t+pd.Timedelta(hours=12))]
  if len(w)<2: continue
  # READY/BUY: capital remains abnormal and price has begun expanding, but not already >10% from watch close
  p0=float(g.iloc[j].close); cond=(w.turn_ratio>=2)&(w.turn_accel_6_24>=.8)&(w.close/p0-1>=.01)&(w.close/p0-1<.10)
  hit=w.index[cond.fillna(False)]
  if len(hit):
   bt=hit[0];sigs.append((bt,m,t));cooldown=bt+pd.Timedelta(hours=72)
s=pd.DataFrame(sigs,columns=['buy_time','market','watch_time']).sort_values('buy_time');print('BUY_SIGNALS',len(s))
by={m:g.set_index('time').sort_index() for m,g in d.groupby('market',sort=False)}
equity=START;busy_until=pd.Timestamp.min.tz_localize('UTC');tr=[]
for z in s.itertuples(index=False):
 if z.buy_time<=busy_until: continue
 g=by[z.market];w=g.loc[(g.index>=z.buy_time)&(g.index<=z.buy_time+pd.Timedelta(hours=72))]
 if len(w)<2: continue
 entry=float(w.close.iloc[0]);peak=entry;exit_t=w.index[-1];exit_p=float(w.close.iloc[-1]);reason='TIME72'
 # HOLD/RELOAD: tolerate pullback while flow survives. SELL: >=8% off running peak plus weak flow; hard protection -12%.
 for t,r in w.iloc[1:].iterrows():
  p=float(r.close);peak=max(peak,p);dd=p/peak-1;ret=p/entry-1
  weak=(r.turn_ratio<1) or (r.turn_accel_6_24<.8)
  if ret<=-.12:
   exit_t=t;exit_p=p;reason='HARD12';break
  if peak/entry-1>=.10 and dd<=-.08 and weak:
   exit_t=t;exit_p=p;reason='FLOW_DD8';break
 gross=exit_p/entry;net=gross*(1-FEE)/(1+FEE);before=equity;equity*=net
 tr.append({'market':z.market,'watch_time':z.watch_time,'buy_time':z.buy_time,'sell_time':exit_t,'entry':entry,'exit':exit_p,'gross_ret':gross-1,'net_ret':net-1,'hold_h':(exit_t-z.buy_time).total_seconds()/3600,'reason':reason,'equity_before':before,'equity_after':equity})
 busy_until=exit_t
r=pd.DataFrame(tr);r.to_csv(OUT+'/trades.csv',index=False)
if len(r):
 eq=np.r_[START,r.equity_after.to_numpy()];run=np.maximum.accumulate(eq);mdd=np.min(eq/run-1);wins=r.net_ret>0;gp=r.loc[r.net_ret>0,'net_ret'].sum();gl=-r.loc[r.net_ret<0,'net_ret'].sum();pf=gp/gl if gl>0 else np.inf
 summary={'start_krw':START,'final_krw':equity,'multiple':equity/START,'trades':len(r),'win_rate':wins.mean(),'avg_net_ret':r.net_ret.mean(),'median_net_ret':r.net_ret.median(),'pf':pf,'mdd':mdd,'avg_hold_h':r.hold_h.mean(),'flow_dd8':(r.reason=='FLOW_DD8').sum(),'hard12':(r.reason=='HARD12').sum(),'time72':(r.reason=='TIME72').sum()}
else:summary={'start_krw':START,'final_krw':START,'multiple':1,'trades':0}
pd.DataFrame([summary]).to_csv(OUT+'/summary.csv',index=False);print(pd.DataFrame([summary]).to_string(index=False))
