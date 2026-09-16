"""CatchWorld Microstructure Engine V4.
Research-only unified causal sensor. No BUY/SELL decisions.
Fixes refill measurement by tracking the SAME price level through time.
"""
from collections import defaultdict,deque
from typing import Any

class MicrostructureEngineV4:
 def __init__(self):
  self.trades=defaultdict(lambda:deque(maxlen=100000));self.books=defaultdict(lambda:deque(maxlen=20000));self.market_flow=deque(maxlen=500000)
 def on_trade(self,t:dict[str,Any]):
  m=t['market'];ts=int(t.get('trade_ts_ms') or t['recv_ms']);self.trades[m].append(t);self.market_flow.append((ts,float(t['notional'])))
  out={'market':m,'ts_ms':ts,'type':'micro_v4'}
  for n,ms in [('1m',60000),('5m',300000),('15m',900000)]:out.update(self._flow(m,ts,ms,n))
  out.update(self._repeat(m,ts));out.update(self._absorb(m,ts));out.update(self._sweep(m,ts));out.update(self._div(m,ts));out.update(self._relative(m,ts));return out
 def on_book(self,b):
  m=b['market'];ts=int(b.get('timestamp') or b['recv_ms']);lv=b.get('levels') or []
  if not lv:return {'market':m,'ts_ms':ts,'type':'book_v4','valid':False}
  snap={'ts':ts,'levels':lv[:15],'tb':float(b.get('total_bid_size') or 0),'ta':float(b.get('total_ask_size') or 0)};self.books[m].append(snap)
  return {'market':m,'ts_ms':ts,'type':'book_v4',**self._book(m,ts)}
 def _tx(self,m,c):return [x for x in self.trades[m] if int(x.get('trade_ts_ms') or x['recv_ms'])>=c]
 def _flow(self,m,ts,ms,n):
  xs=self._tx(m,ts-ms);buy=sum(float(x['notional']) for x in xs if x['side']=='BID');sell=sum(float(x['notional']) for x in xs if x['side']=='ASK');tot=buy+sell
  r=float(xs[-1]['price'])/float(xs[0]['price'])-1 if xs and float(xs[0]['price']) else 0
  return {f'notional_{n}':tot,f'delta_{n}':buy-sell,f'delta_ratio_{n}':(buy-sell)/tot if tot else 0,f'ret_{n}':r,f'efficiency_{n}':abs(r)/(tot/1e8) if tot else None}
 def _repeat(self,m,ts):
  xs=self._tx(m,ts-60000);best=[]
  for x in xs:
   n=float(x['notional']);g=[y for y in xs if y['side']==x['side'] and n>0 and abs(float(y['notional'])/n-1)<=.05]
   if len(g)>len(best):best=g
  return {'repeat_count_60s':len(best) if len(best)>=6 else 0,'repeat_side':best[0]['side'] if len(best)>=6 else None,'repeat_sum':sum(float(x['notional']) for x in best) if len(best)>=6 else 0}
 def _absorb(self,m,ts):
  flags=[]
  for k in range(5):
   xs=[x for x in self.trades[m] if ts-(k+1)*60000<int(x.get('trade_ts_ms') or x['recv_ms'])<=ts-k*60000]
   if len(xs)<2:continue
   b=sum(float(x['notional']) for x in xs if x['side']=='BID');s=sum(float(x['notional']) for x in xs if x['side']=='ASK');z=b+s;r=float(xs[-1]['price'])/float(xs[0]['price'])-1;im=(b-s)/z if z else 0;flags.append((im<=-.25 and r>-.0025,im>=.25 and r<.0025))
  return {'down_absorb_minutes_5m':sum(a for a,_ in flags),'up_absorb_minutes_5m':sum(a for _,a in flags)}
 def _sweep(self,m,ts):
  xs=self._tx(m,ts-10000);b=[x for x in xs if x['side']=='BID'];a=[x for x in xs if x['side']=='ASK'];return {'bid_sweep':len(b)>=3 and len({float(x['price']) for x in b})>=3,'ask_sweep':len(a)>=3 and len({float(x['price']) for x in a})>=3}
 def _div(self,m,ts):
  xs=self._tx(m,ts-300000)
  if len(xs)<10:return {'bull_cvd_div':False,'bear_cvd_div':False}
  k=len(xs)//2;a,b=xs[:k],xs[k:];delta=lambda z:sum(float(x['notional'])*(1 if x['side']=='BID' else -1) for x in z);pr=float(b[-1]['price'])/float(a[-1]['price'])-1;dd=delta(b)-delta(a);return {'bull_cvd_div':dd>0 and pr<=0,'bear_cvd_div':dd<0 and pr>=0,'cvd_delta_change_5m':dd}
 def _relative(self,m,ts):
  coin=sum(float(x['notional']) for x in self._tx(m,ts-300000));alln=sum(n for t,n in self.market_flow if t>=ts-300000);return {'market_relative_flow_5m':coin/alln if alln else 0}
 def _book(self,m,ts):
  xs=[x for x in self.books[m] if x['ts']>=ts-60000];last=xs[-1];cur_bid=float(last['levels'][0]['bid_price']);cur_ask=float(last['levels'][0]['ask_price'])
  def same(side,price):
   keyp=side+'_price';keys=side+'_size';return [(x['ts'],float(u[keys])) for x in xs for u in x['levels'] if u.get(keyp) is not None and float(u[keyp])==price and u.get(keys) is not None]
  def refill(hist):
   if len(hist)<3:return (1.,False,0)
   vals=[v for _,v in hist];mi=min(range(len(vals)),key=vals.__getitem__);ratio=vals[-1]/vals[mi] if vals[mi]>0 and mi<len(vals)-1 else 1.;rebuild=sum(vals[i]>vals[i-1] for i in range(mi+1,len(vals)));return ratio,ratio>=1.5,rebuild
  bh=same('bid',cur_bid);ah=same('ask',cur_ask);br,bref,bc=refill(bh);ar,aref,ac=refill(ah);tb=last['tb'];ta=last['ta']
  return {'valid':True,'best_bid':cur_bid,'best_ask':cur_ask,'bid_refill_ratio_same_price_60s':br,'ask_refill_ratio_same_price_60s':ar,'bid_refill_same_price':bref,'ask_refill_same_price':aref,'iceberg_bid_suspect':bref and bc>=3,'iceberg_ask_suspect':aref and ac>=3,'book_imbalance':(tb-ta)/(tb+ta) if tb+ta else 0}
