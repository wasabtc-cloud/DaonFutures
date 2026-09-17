"""Strategy A multi-timeframe 1-month benchmark.
Research benchmark: same A concept on 60/30/15/5/3/1 minute bars.
Starting equity 1,000,000 KRW, one position at a time, fee 0.05%/side,
TP +3%, SL -1.5%, max hold 6 hours. No slippage.

Important: A's original ret30 is a 30-minute return, so it remains a 30-minute
lookback at every bar resolution rather than being reinterpreted as 30 bars.
Flow is turnover acceleration: current bar turnover / rolling baseline turnover.
This benchmark downloads the latest ~31 days of Upbit KRW candles and evaluates
all resolutions independently. Results are research estimates, not tick fills.
"""
from __future__ import annotations
import time, math
from pathlib import Path
import requests, pandas as pd, numpy as np

START=1_000_000.0; FEE=.0005; TP=.03; SL=.015; HOLD_MIN=360
TFS=[60,30,15,5,3,1]
OUT=Path('results/strategy_a_multitimeframe_1m'); OUT.mkdir(parents=True,exist_ok=True)
S=requests.Session(); S.headers.update({'User-Agent':'CatchWorld-Research/1.0'})
BASE='https://api.upbit.com/v1'

def get_json(url,params=None,retries=8):
 for i in range(retries):
  r=S.get(url,params=params,timeout=20)
  if r.status_code==429: time.sleep(min(2**i,15)); continue
  r.raise_for_status(); return r.json()
 raise RuntimeError(url)

def markets():
 x=get_json(BASE+'/market/all')
 return sorted([z['market'] for z in x if z['market'].startswith('KRW-')])

def candles(m,unit,start,end):
 rows=[]; to=end
 # Upbit returns max 200 candles per call. Walk backward until start.
 while to>start:
  x=get_json(f'{BASE}/candles/minutes/{unit}',{'market':m,'count':200,'to':to.strftime('%Y-%m-%dT%H:%M:%SZ')})
  if not x: break
  rows.extend(x); oldest=pd.to_datetime(x[-1]['candle_date_time_utc'],utc=True)
  if oldest<=start: break
  to=oldest-pd.Timedelta(seconds=1); time.sleep(.11)
 d=pd.DataFrame(rows)
 if d.empty: return d
 d['time']=pd.to_datetime(d.candle_date_time_utc,utc=True)
 d=d[(d.time>=start)&(d.time<=end)].drop_duplicates('time').sort_values('time')
 return d[['time','opening_price','high_price','low_price','trade_price','candle_acc_trade_price']].rename(columns={'opening_price':'open','high_price':'high','low_price':'low','trade_price':'close','candle_acc_trade_price':'turnover'})

def signals(d,unit):
 if d.empty: return d
 q=d.copy().set_index('time')
 # exact 30-minute price change using as-of observations at/before t-30m
 idx=q.index
 old=q[['close']].reset_index().rename(columns={'time':'old_time','close':'old_close'})
 target=pd.DataFrame({'time':idx,'target':idx-pd.Timedelta(minutes=30)})
 a=pd.merge_asof(target.sort_values('target'),old.sort_values('old_time'),left_on='target',right_on='old_time',direction='backward')
 a=a.set_index('time').reindex(idx)
 q['ret30']=q.close/a.old_close-1
 # scale baseline to ~24h, minimum enough observations
 n=max(24,round(24*60/unit))
 base=q.turnover.shift(1).rolling(n,min_periods=max(12,n//4)).median()
 q['flow']=q.turnover/base.replace(0,np.nan)
 kst=q.index+pd.Timedelta(hours=9)
 q['kst_hour']=kst.hour
 return q.reset_index()

def run_tf(unit,ms,start,end):
 allsig=[]; paths={}
 for j,m in enumerate(ms,1):
  try: d=candles(m,unit,start-pd.Timedelta(days=1),end)
  except Exception as e: print('FETCH_FAIL',unit,m,type(e).__name__,flush=True); continue
  if d.empty: continue
  q=signals(d,unit); paths[m]=q
  e=q[(q.flow>=10)&q.ret30.between(-.025,-.020)&q.kst_hour.between(6,8)&(q.time>=start)].copy()
  if not e.empty: e['market']=m; allsig.append(e[['market','time','flow','ret30','close']])
  if j%20==0: print('TF',unit,'markets',j,'signals',sum(len(x) for x in allsig),flush=True)
 if not allsig: return {'tf_min':unit,'raw_signals':0,'trades':0,'final_krw':START,'multiple':1,'win_pct':np.nan,'avg_net_pct':np.nan,'pf':np.nan,'mdd_pct':0},pd.DataFrame()
 e=pd.concat(allsig).sort_values(['time','flow'],ascending=[True,False])
 equity=START; free=pd.Timestamp.min.tz_localize('UTC'); tr=[]
 for _,r in e.iterrows():
  if r.time<free: continue
  q=paths[r.market]; fut=q[(q.time>r.time)&(q.time<=r.time+pd.Timedelta(minutes=HOLD_MIN))]
  if fut.empty: continue
  ep=float(r.close); ex=float(fut.iloc[-1].close); reason='TIME'; et=fut.iloc[-1].time
  # OHLC ambiguity: if both TP and SL in same bar, count SL first (conservative).
  for _,b in fut.iterrows():
   if float(b.low)<=ep*(1-SL): ex=ep*(1-SL); reason='SL'; et=b.time; break
   if float(b.high)>=ep*(1+TP): ex=ep*(1+TP); reason='TP'; et=b.time; break
  gross=ex/ep-1; nr=(1+gross)*(1-FEE)/(1+FEE)-1
  before=equity; equity*=1+nr; free=et
  tr.append({'tf_min':unit,'market':r.market,'entry_time':r.time,'exit_time':et,'flow':r.flow,'ret30':r.ret30,'reason':reason,'net_ret':nr,'equity_before':before,'equity_after':equity})
 t=pd.DataFrame(tr)
 if t.empty: return {'tf_min':unit,'raw_signals':len(e),'trades':0,'final_krw':START,'multiple':1,'win_pct':np.nan,'avg_net_pct':np.nan,'pf':np.nan,'mdd_pct':0},t
 v=t.net_ret; gains=v[v>0].sum(); losses=-v[v<0].sum(); peak=pd.concat([pd.Series([START]),t.equity_after],ignore_index=True).cummax().iloc[1:].set_axis(t.index); dd=t.equity_after/peak-1
 return {'tf_min':unit,'raw_signals':len(e),'trades':len(t),'final_krw':equity,'multiple':equity/START,'win_pct':100*(v>0).mean(),'avg_net_pct':100*v.mean(),'pf':gains/losses if losses>0 else np.nan,'mdd_pct':100*dd.min(),'tp_pct':100*(t.reason=='TP').mean(),'sl_pct':100*(t.reason=='SL').mean(),'time_pct':100*(t.reason=='TIME').mean()},t

def main():
 end=pd.Timestamp.now(tz='UTC').floor('min'); start=end-pd.Timedelta(days=30)
 ms=markets(); print('PERIOD',start,end,'MARKETS',len(ms),flush=True)
 sums=[]; led=[]
 for u in TFS:
  print('START_TF',u,flush=True); s,t=run_tf(u,ms,start,end); sums.append(s)
  if not t.empty: led.append(t)
  pd.DataFrame(sums).to_csv(OUT/'summary_partial.csv',index=False)
  print('RESULT',s,flush=True)
 pd.DataFrame(sums).to_csv(OUT/'summary.csv',index=False)
 if led: pd.concat(led,ignore_index=True).to_csv(OUT/'ledger.csv',index=False)
 print(pd.DataFrame(sums).to_string(index=False),flush=True)
if __name__=='__main__': main()
