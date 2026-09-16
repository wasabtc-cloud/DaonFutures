"""CatchWorld causal state engine V1.
Consumes validated candle + microstructure features. Research state machine only.
Thresholds are placeholders to validate chronologically, not production trading rules.
"""
from dataclasses import dataclass
@dataclass
class State:
 name:str='DORMANT';peak:float=0.;last_price:float=0.
class CatchWorldStateEngine:
 def __init__(self):self.s={}
 def update(self,market:str,f:dict)->dict:
  s=self.s.setdefault(market,State());p=float(f.get('price') or f.get('close') or s.last_price or 0);prev=s.name
  flow=float(f.get('turn_ratio',0) or 0);ret24=float(f.get('ret_24h',0) or 0);hl=bool(f.get('higher_low',False));breakout=bool(f.get('short_high_break',False))
  absorb=int(f.get('down_absorb_minutes_5m',0) or 0);refill=bool(f.get('bid_refill_same_price',False));cvd=bool(f.get('bull_cvd_div',False));sweep=bool(f.get('bid_sweep',False))
  # Discovery: activity before an already-hot move. Microstructure strengthens READY but is not proof of accumulation.
  if s.name=='DORMANT' and flow>=2 and -.07<=ret24<=.03:s.name='WATCH'
  elif s.name=='WATCH' and (absorb>=2 or refill or cvd):s.name='READY'
  elif s.name=='READY' and hl and breakout and (sweep or flow>=2):s.name='BUY'
  elif s.name=='BUY':s.name='HOLD'
  elif s.name=='HOLD':
   s.peak=max(s.peak,p)
   if bool(f.get('pullback',False)) and (absorb>=1 or refill):s.name='RELOAD'
   if bool(f.get('hl_break',False)) and (bool(f.get('bear_cvd_div',False)) or bool(f.get('flow_decay',False))):s.name='SELL'
  elif s.name=='RELOAD' and hl and breakout:s.name='HOLD'
  elif s.name=='SELL':s.name='DORMANT';s.peak=0
  s.last_price=p
  return {'market':market,'previous':prev,'state':s.name,'price':p,'changed':prev!=s.name}
