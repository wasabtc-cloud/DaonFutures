"""Strategy A multi-timeframe 1-month benchmark, optimized.
Download 1m candles once per KRW market, then resample locally to 3/5/15/30/60m.
Starting equity 1,000,000 KRW, one position at a time, fee 0.05%/side,
TP +3%, SL -1.5%, max hold 6 hours. No slippage.
ret30 remains an actual 30-minute return at every resolution.
"""
from __future__ import annotations
import time
from pathlib import Path
import requests, pandas as pd, numpy as np

START=1_000_000.0; FEE=.0005; TP=.03; SL=.015; HOLD_MIN=360
TFS=[60,30,15,5,3,1]
OUT=Path('results/strategy_a_multitimeframe_1m'); OUT.mkdir(parents=True,exist_ok=True)
CACHE=Path('data/strategy_a_1m_cache'); CACHE.mkdir(parents=True,exist_ok=True)
S=requests.Session(); S.headers.update({'User-Agent':'CatchWorld-Research/1.1'})
BASE='https://api.upbit.com/v1'

def get_json(url,params=None,retries=10):
 for i in range(retries):
  try:
   r=S.get(url,params=params,timeout=25)
   if r.status_code==429: time.sleep(min(.5*(i+1),5)); continue
   r.raise_for_status(); return r.json()
  except requests.RequestException:
   if i==retries-1: raise
   time.sleep(min(.5*(i+1),5))
 raise RuntimeError(url)

def markets():
 return sorted(z['market'] for z in get_json(BASE+'/market/all') if z['market'].startswith('KRW-'))

def candles_1m(m,start,end):
 rows=[]; to=end
 while to>start:
  x=get_json(BASE+'/candles/minutes/1',{'market':m,'count':200,'to':to.strftime('%Y-%m-%dT%H:%M:%SZ')})
  if not x: break
  rows.extend(x); oldest=pd.to_datetime(x[-1]['candle_date_time_utc'],utc=True)
  if oldest<=start: break
  to=oldest-pd.Timedelta(seconds=1); time.sleep(.105)
 d=pd.DataFrame(rows)
 if d.empty: return d
 d['time']=pd.to_datetime(d.candle_date_time_utc,utc=True)
 d=d[(d.time>=start)&(d.time<=end)].drop_duplicates('time').sort_values('time')
 return d[['time','opening_price','high_price','low_price','trade_price','candle_acc_trade_price']].rename(columns={'opening_price':'open','high_price':'high','low_price':'low','trade_price':'close','candle_acc_trade_price':'turnover'})

def resample(d,u):
 if u==1: return d.copy()
 q=d.set_index('time').resample(f'{u}min',label='left',closed='left').agg({'open':'first','high':'max','low':'min','close':'last','turnover':'sum'}).dropna(subset=['open','close']).reset_index()
 return q

def add_features(d,u):
 q=d.copy().set_index('time')
 old=q[['close']].reset_index().rename(columns={'time':'old_time','close':'old_close'})
 target=pd.DataFrame({'time':q.index,'target':q.index-pd.Timedelta(minutes=30)})
 a=pd.merge_asof(target.sort_values('target'),old.sort_values('old_time'),left_on='target',right_on='old_time',direction='backward').set_index('time').reindex(q.index)
 q['ret30']=q.close/a.old_close-1
 n=max(24,round(24*60/u)); base=q.turnover.shift(1).rolling(n,min_periods=max(12,n//4)).median()
 q['flow']=q.turnover/base.replace(0,np.nan)
 q['kst_hour']=(q.index+pd.Timedelta(hours=9)).hour
 return q.reset_index()

def simulate(unit,frames,start):
 allsig=[]
 for m,q in frames.items():
  e=q[(q.flow>=10)&q.ret30.between(-.025,-.020)&q.kst_hour.between(6,8)&(q.time>=start)].copy()
  if not e.empty: e['market']=m; allsig.append(e[['market','time','flow','ret30','close']])
 if not allsig: return {'tf_min':unit,'raw_signals':0,'trades':0,'final_krw':START,'multiple':1,'win_pct':np.nan,'avg_net_pct':np.nan,'pf':np.nan,'mdd_pct':0},pd.DataFrame()
 e=pd.concat(allsig).sort_values(['time','flow'],ascending=[True,False]); equity=START; free=pd.Timestamp.min.tz_localize('UTC'); tr=[]
 for _,r in e.iterrows():
  if r.time<free: continue
  q=frames[r.market]; fut=q[(q.time>r.time)&(q.time<=r.time+pd.Timedelta(minutes=HOLD_MIN))]
  if fut.empty: continue
  ep=float(r.close); ex=float(fut.iloc[-1].close); reason='TIME'; et=fut.iloc[-1].time
  for _,b in fut.iterrows():
   if float(b.low)<=ep*(1-SL): ex=ep*(1-SL); reason='SL'; et=b.time; break
   if float(b.high)>=ep*(1+TP): ex=ep*(1+TP); reason='TP'; et=b.time; break
  nr=(ex/ep)*(1-FEE)/(1+FEE)-1; before=equity; equity*=1+nr; free=et
  tr.append({'tf_min':unit,'market':r.market,'entry_time':r.time,'exit_time':et,'flow':r.flow,'ret30':r.ret30,'reason':reason,'net_ret':nr,'equity_before':before,'equity_after':equity})
 t=pd.DataFrame(tr); base={'tf_min':unit,'raw_signals':len(e)}
 if t.empty: return {**base,'trades':0,'final_krw':START,'multiple':1,'win_pct':np.nan,'avg_net_pct':np.nan,'pf':np.nan,'mdd_pct':0},t
 v=t.net_ret; gains=v[v>0].sum(); losses=-v[v<0].sum(); peak=pd.concat([pd.Series([START]),t.equity_after],ignore_index=True).cummax().iloc[1:].set_axis(t.index); dd=t.equity_after/peak-1
 return {**base,'trades':len(t),'final_krw':equity,'multiple':equity/START,'win_pct':100*(v>0).mean(),'avg_net_pct':100*v.mean(),'pf':gains/losses if losses>0 else np.nan,'mdd_pct':100*dd.min(),'tp_pct':100*(t.reason=='TP').mean(),'sl_pct':100*(t.reason=='SL').mean(),'time_pct':100*(t.reason=='TIME').mean()},t

def main():
 end=pd.Timestamp.now(tz='UTC').floor('min'); start=end-pd.Timedelta(days=30); fetch_start=start-pd.Timedelta(days=1)
 ms=markets(); print('PERIOD',start,end,'MARKETS',len(ms),flush=True)
 raw={}
 for j,m in enumerate(ms,1):
  try: d=candles_1m(m,fetch_start,end)
  except Exception as ex: print('FETCH_FAIL',m,type(ex).__name__,flush=True); continue
  if not d.empty: raw[m]=d
  if j%10==0: print('FETCHED_1M',j,'/',len(ms),'usable',len(raw),flush=True)
 print('DOWNLOAD_DONE',len(raw),flush=True)
 sums=[]; led=[]
 for u in TFS:
  print('START_TF',u,flush=True); frames={m:add_features(resample(d,u),u) for m,d in raw.items()}
  s,t=simulate(u,frames,start); sums.append(s)
  if not t.empty: led.append(t)
  pd.DataFrame(sums).to_csv(OUT/'summary_partial.csv',index=False); print('RESULT',s,flush=True)
 pd.DataFrame(sums).to_csv(OUT/'summary.csv',index=False)
 if led: pd.concat(led,ignore_index=True).to_csv(OUT/'ledger.csv',index=False)
 print(pd.DataFrame(sums).to_string(index=False),flush=True)
if __name__=='__main__': main()
