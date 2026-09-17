"""Strategy A2: multi-TF confirmation experiment.
Preserves A1. 1m data -> 3/5/15/60m locally. Same 1M KRW account, 0.05%/side.
DEV experiment: compare A1 3m baseline vs 3m triggers confirmed by 5/15/60m context.
Also records 6h MFE/MAE for every executed trade. No slippage; conservative SL-first.
"""
from __future__ import annotations
import time
from pathlib import Path
import requests, pandas as pd, numpy as np
START=1_000_000.; FEE=.0005; HOLD=360
OUT=Path('results/strategy_a2_multitf'); OUT.mkdir(parents=True,exist_ok=True)
S=requests.Session(); S.headers.update({'User-Agent':'CatchWorld-A2/1.0'}); BASE='https://api.upbit.com/v1'

def gj(url,params=None):
 for i in range(10):
  try:
   r=S.get(url,params=params,timeout=25)
   if r.status_code==429: time.sleep(min(.5*(i+1),5)); continue
   r.raise_for_status(); return r.json()
  except requests.RequestException:
   if i==9: raise
   time.sleep(min(.5*(i+1),5))

def markets(): return sorted(x['market'] for x in gj(BASE+'/market/all') if x['market'].startswith('KRW-'))
def candles(m,start,end):
 rows=[]; to=end
 while to>start:
  x=gj(BASE+'/candles/minutes/1',{'market':m,'count':200,'to':to.strftime('%Y-%m-%dT%H:%M:%SZ')})
  if not x: break
  rows+=x; old=pd.to_datetime(x[-1]['candle_date_time_utc'],utc=True)
  if old<=start: break
  to=old-pd.Timedelta(seconds=1); time.sleep(.105)
 d=pd.DataFrame(rows)
 if d.empty:return d
 d['time']=pd.to_datetime(d.candle_date_time_utc,utc=True)
 d=d[(d.time>=start)&(d.time<=end)].drop_duplicates('time').sort_values('time')
 return d[['time','opening_price','high_price','low_price','trade_price','candle_acc_trade_price']].rename(columns={'opening_price':'open','high_price':'high','low_price':'low','trade_price':'close','candle_acc_trade_price':'turnover'})
def rs(d,u):
 if u==1:return d.copy()
 return d.set_index('time').resample(f'{u}min',label='left',closed='left').agg(open=('open','first'),high=('high','max'),low=('low','min'),close=('close','last'),turnover=('turnover','sum')).dropna().reset_index()
def feat(d,u):
 q=d.copy().set_index('time'); old=q[['close']].reset_index().rename(columns={'time':'ot','close':'oc'})
 z=pd.DataFrame({'time':q.index,'target':q.index-pd.Timedelta(minutes=30)})
 a=pd.merge_asof(z.sort_values('target'),old.sort_values('ot'),left_on='target',right_on='ot',direction='backward').set_index('time').reindex(q.index)
 q['ret30']=q.close/a.oc-1; n=max(24,round(1440/u)); base=q.turnover.shift(1).rolling(n,min_periods=max(12,n//4)).median(); q['flow']=q.turnover/base.replace(0,np.nan); q['kst_hour']=(q.index+pd.Timedelta(hours=9)).hour
 return q.reset_index()
def sig(q): return (q.flow>=10)&q.ret30.between(-.025,-.020)&q.kst_hour.between(6,8)
def prior_signal(q,t,minutes):
 x=q[(q.time<=t)&(q.time>=t-pd.Timedelta(minutes=minutes))]
 return bool((sig(x)).any()) if len(x) else False
def run(name,frames,confirm,TP=.03,SL=.015):
 ev=[]
 for m,f in frames.items():
  q=f[3]; e=q[sig(q)].copy()
  for _,r in e.iterrows():
   ok=True
   for u,w in confirm: ok &= prior_signal(f[u],r.time,w)
   if ok: ev.append((r.time,float(r.flow),m,float(r.close),float(r.ret30)))
 ev.sort(key=lambda x:(x[0],-x[1])); eq=START; free=pd.Timestamp.min.tz_localize('UTC'); tr=[]
 for t,flow,m,ep,ret30 in ev:
  if t<free:continue
  q=frames[m][1]; fut=q[(q.time>t)&(q.time<=t+pd.Timedelta(minutes=HOLD))]
  if fut.empty:continue
  mfe=(fut.high.max()/ep-1); mae=(fut.low.min()/ep-1); ex=float(fut.iloc[-1].close); reason='TIME'; et=fut.iloc[-1].time
  for _,b in fut.iterrows():
   if b.low<=ep*(1-SL): ex=ep*(1-SL); reason='SL'; et=b.time; break
   if b.high>=ep*(1+TP): ex=ep*(1+TP); reason='TP'; et=b.time; break
  nr=(ex/ep)*(1-FEE)/(1+FEE)-1; before=eq; eq*=1+nr; free=et
  tr.append(dict(variant=name,market=m,entry_time=t,exit_time=et,flow=flow,ret30=ret30,mfe_pct=100*mfe,mae_pct=100*mae,reason=reason,net_ret=nr,equity_before=before,equity_after=eq))
 d=pd.DataFrame(tr)
 if d.empty:return dict(variant=name,signals=len(ev),trades=0,final_krw=START,pf=np.nan,mdd_pct=0,win_pct=np.nan),d
 v=d.net_ret; peak=pd.concat([pd.Series([START]),d.equity_after],ignore_index=True).cummax().iloc[1:].set_axis(d.index); dd=d.equity_after/peak-1
 return dict(variant=name,signals=len(ev),trades=len(d),final_krw=eq,return_pct=100*(eq/START-1),win_pct=100*(v>0).mean(),pf=v[v>0].sum()/(-v[v<0].sum()) if (v<0).any() else np.nan,mdd_pct=100*dd.min(),mfe_med_pct=d.mfe_pct.median(),mae_med_pct=d.mae_pct.median()),d
def main():
 end=pd.Timestamp.now(tz='UTC').floor('min'); start=end-pd.Timedelta(days=30); fs=start-pd.Timedelta(days=1); raw={}; ms=markets(); print('A2_PERIOD',start,end,'MARKETS',len(ms),flush=True)
 for i,m in enumerate(ms,1):
  try:d=candles(m,fs,end)
  except Exception as e: print('FAIL',m,type(e).__name__,flush=True);continue
  if not d.empty:raw[m]=d
  if i%10==0:print('FETCH',i,len(ms),len(raw),flush=True)
 frames={}
 for m,d in raw.items(): frames[m]={u:feat(rs(d,u),u) for u in [1,3,5,15,60]}
 variants=[('A1_3m',[]),('A2_3+5',[(5,10)]),('A2_3+15',[(15,30)]),('A2_3+5+15',[(5,10),(15,30)]),('A2_3+15+60',[(15,30),(60,120)]),('A2_3+5+15+60',[(5,10),(15,30),(60,120)])]
 sums=[]; led=[]
 for n,c in variants:
  s,d=run(n,frames,c); sums.append(s); print('RESULT',s,flush=True)
  if not d.empty:led.append(d)
 pd.DataFrame(sums).to_csv(OUT/'summary.csv',index=False)
 if led:pd.concat(led,ignore_index=True).to_csv(OUT/'ledger.csv',index=False)
 print(pd.DataFrame(sums).to_string(index=False),flush=True)
if __name__=='__main__':main()
