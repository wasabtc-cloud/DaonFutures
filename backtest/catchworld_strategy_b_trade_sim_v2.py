import glob,os
import numpy as np,pandas as pd
OUT='results/strategy_b_trade_sim_v2';os.makedirs(OUT,exist_ok=True)
FEE=.0005;START=1_000_000.0
fs=glob.glob('strategy_b_input/**/*.csv',recursive=True);d=pd.concat([pd.read_csv(f) for f in fs],ignore_index=True)
d.time=pd.to_datetime(d.time,utc=True,errors='coerce');d=d.dropna(subset=['time']).drop_duplicates(['market','time']).sort_values(['market','time'])
for c in ['close','turn_ratio','turn_accel_6_24','ret_6h','ret_12h','ret_24h','ret_72h','ret_168h','ret_336h','ret_720h','range24','range72','drawdown_30d']:
 if c in d:d[c]=pd.to_numeric(d[c],errors='coerce')
# V2: keep WATCH broad, but split READY into two empirically observed pre-pump states.
# REVERSAL = deeply depressed coin beginning to recover. TREND = already recovering/positive structure.
# BUY requires sustained flow plus price response; no future labels are used.
sigs=[]
for m,g in d.groupby('market',sort=False):
 g=g.set_index('time').sort_index();base=((g.turn_ratio>=4)&(g.ret_24h<.10)).astype(int);watch=base.rolling('48h',min_periods=1).sum()>=3
 cooldown=None
 for j in np.flatnonzero(watch.to_numpy()):
  t=g.index[j]
  if cooldown is not None and t<cooldown:continue
  r0=g.iloc[j];p0=float(r0.close)
  # Two broad states found in the 1,153-event analysis; thresholds are deliberately broad, then ignition confirms.
  reversal=(r0.drawdown_30d<=-.22) and (r0.ret_168h<=0)
  trend=(r0.drawdown_30d>-.22) and (r0.ret_72h>0) and (r0.ret_24h>-.02)
  if not (reversal or trend):continue
  typ='REVERSAL' if reversal else 'TREND'
  w=g.loc[(g.index>t)&(g.index<=t+pd.Timedelta(hours=12))]
  if len(w)<3:continue
  # Sustained flow: current abnormal flow and recent 3h median stays elevated.
  med3=w.turn_ratio.rolling(3,min_periods=2).median()
  price_resp=w.close/p0-1
  # Reversal needs stronger reclaim; trend can trigger earlier but must keep positive 24h structure.
  if typ=='REVERSAL': cond=(w.turn_ratio>=2.5)&(med3>=2)&(w.turn_accel_6_24>=.8)&(price_resp>=.02)&(price_resp<.10)&(w.ret_6h>0)
  else: cond=(w.turn_ratio>=2)&(med3>=1.8)&(w.turn_accel_6_24>=.8)&(price_resp>=.01)&(price_resp<.08)&(w.ret_6h>0)&(w.ret_24h>0)
  hit=w.index[cond.fillna(False)]
  if len(hit):
   bt=hit[0];sigs.append((bt,m,t,typ));cooldown=bt+pd.Timedelta(hours=72)
s=pd.DataFrame(sigs,columns=['buy_time','market','watch_time','setup']).sort_values('buy_time');print('BUY_SIGNALS',len(s));print(s.setup.value_counts().to_string() if len(s) else '')
by={m:g.set_index('time').sort_index() for m,g in d.groupby('market',sort=False)}
equity=START;busy_until=pd.Timestamp.min.tz_localize('UTC');tr=[]
for z in s.itertuples(index=False):
 if z.buy_time<=busy_until:continue
 g=by[z.market];w=g.loc[(g.index>=z.buy_time)&(g.index<=z.buy_time+pd.Timedelta(hours=72))]
 if len(w)<2:continue
 entry=float(w.close.iloc[0]);peak=entry;exit_t=w.index[-1];exit_p=float(w.close.iloc[-1]);reason='TIME72';weak_streak=0
 for t,r in w.iloc[1:].iterrows():
  p=float(r.close);peak=max(peak,p);ret=p/entry-1;dd=p/peak-1
  weak=((r.turn_ratio<1.2) or (r.turn_accel_6_24<.75)) and (r.ret_6h<0)
  weak_streak=weak_streak+1 if weak else 0
  # Earlier protection fixes V1's long dead holds. Give genuine runners room after +10%.
  if ret<=-.07:
   exit_t=t;exit_p=p;reason='HARD7';break
  if (t-z.buy_time)>=pd.Timedelta(hours=12) and peak/entry-1<.04 and weak_streak>=3:
   exit_t=t;exit_p=p;reason='DEAD12';break
  if peak/entry-1>=.10 and dd<=-.08 and weak_streak>=2:
   exit_t=t;exit_p=p;reason='FLOW_DD8';break
  if (t-z.buy_time)>=pd.Timedelta(hours=36) and peak/entry-1<.10 and ret<0 and weak_streak>=2:
   exit_t=t;exit_p=p;reason='WEAK36';break
 gross=exit_p/entry;net=gross*(1-FEE)/(1+FEE);before=equity;equity*=net
 tr.append({'market':z.market,'setup':z.setup,'watch_time':z.watch_time,'buy_time':z.buy_time,'sell_time':exit_t,'entry':entry,'exit':exit_p,'gross_ret':gross-1,'net_ret':net-1,'hold_h':(exit_t-z.buy_time).total_seconds()/3600,'reason':reason,'equity_before':before,'equity_after':equity});busy_until=exit_t
r=pd.DataFrame(tr);r.to_csv(OUT+'/trades.csv',index=False)
if len(r):
 eq=np.r_[START,r.equity_after.to_numpy()];run=np.maximum.accumulate(eq);mdd=np.min(eq/run-1);gp=r.loc[r.net_ret>0,'net_ret'].sum();gl=-r.loc[r.net_ret<0,'net_ret'].sum();pf=gp/gl if gl>0 else np.inf
 summary={'start_krw':START,'final_krw':equity,'multiple':equity/START,'trades':len(r),'win_rate':(r.net_ret>0).mean(),'avg_net_ret':r.net_ret.mean(),'median_net_ret':r.net_ret.median(),'pf':pf,'mdd':mdd,'avg_hold_h':r.hold_h.mean(),'reversal':(r.setup=='REVERSAL').sum(),'trend':(r.setup=='TREND').sum(),'flow_dd8':(r.reason=='FLOW_DD8').sum(),'hard7':(r.reason=='HARD7').sum(),'dead12':(r.reason=='DEAD12').sum(),'weak36':(r.reason=='WEAK36').sum(),'time72':(r.reason=='TIME72').sum()}
else:summary={'start_krw':START,'final_krw':START,'multiple':1,'trades':0}
pd.DataFrame([summary]).to_csv(OUT+'/summary.csv',index=False);print(pd.DataFrame([summary]).to_string(index=False))
if len(r):print('\nBY_SETUP\n',r.groupby('setup').net_ret.agg(['count','mean','median']).to_string());print('\nBY_EXIT\n',r.groupby('reason').net_ret.agg(['count','mean','median']).to_string())
