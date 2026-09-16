"""One-account chronological simulator. Strategy-independent execution/accounting shell.
No signal thresholds are embedded. Signals must be causal and externally validated first.
"""
from dataclasses import dataclass
@dataclass
class Result:
 start_cash:float;final_cash:float;trades:int;wins:int;max_drawdown:float

def simulate(signals,start_cash=1_000_000.0,fee_rate=.0005):
 """signals: chronological dicts {entry_time,exit_time,entry_price,exit_price}; overlapping entries ignored."""
 ss=sorted(signals,key=lambda x:x['entry_time']);cash=start_cash;busy_until=None;peak=cash;mdd=0.;n=w=0
 for s in ss:
  if busy_until is not None and s['entry_time']<busy_until:continue
  ep=float(s['entry_price']);xp=float(s['exit_price'])
  if ep<=0 or xp<=0:continue
  net=(1-fee_rate)*(xp/ep)*(1-fee_rate);before=cash;cash*=net;n+=1;w+=cash>before;peak=max(peak,cash);mdd=min(mdd,cash/peak-1);busy_until=s['exit_time']
 return Result(start_cash,cash,n,w,mdd)
