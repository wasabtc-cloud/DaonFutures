"""CatchWorld Microstructure Sensor V3 — research sensors, not trading rules.

Adds causal features to V2 for later pump-vs-control validation:
price efficiency, CVD divergence, persistent absorption, refill/iceberg suspicion,
sweep, liquidity vacuum, and market-relative flow.
"""
from __future__ import annotations
from collections import defaultdict, deque
from statistics import median
from typing import Any

class MicrostructureSensorV3:
    def __init__(self):
        self.trades = defaultdict(lambda: deque(maxlen=100000))
        self.books = defaultdict(lambda: deque(maxlen=20000))
        self.market_notional = deque(maxlen=300000)

    def trade(self, t: dict[str, Any]) -> dict[str, Any]:
        m=t['market']; ts=int(t.get('trade_ts_ms') or t['recv_ms']); self.trades[m].append(t)
        self.market_notional.append((ts,float(t['notional'])))
        x1=self._tx(m,ts-60000); x5=self._tx(m,ts-300000); x15=self._tx(m,ts-900000)
        o={'market':m,'ts_ms':ts,'type':'micro_v3'}
        for name,xs in [('1m',x1),('5m',x5),('15m',x15)]: o.update(self._flow(xs,name))
        o.update(self._divergence(x5)); o.update(self._persistent_absorption(m,ts)); o.update(self._sweep(m,ts));
        o.update(self._relative_flow(m,ts,x5)); return o

    def book(self,b:dict[str,Any])->dict[str,Any]:
        m=b['market']; ts=int(b.get('timestamp') or b['recv_ms']); lv=b.get('levels') or []
        if not lv:return {'market':m,'ts_ms':ts,'valid':False}
        snap={'ts':ts,'bid':float(lv[0]['bid_price']),'ask':float(lv[0]['ask_price']),
              'bid_size':float(lv[0]['bid_size']),'ask_size':float(lv[0]['ask_size']),
              'tb':float(b.get('total_bid_size') or 0),'ta':float(b.get('total_ask_size') or 0),
              'levels':lv[:15]}; self.books[m].append(snap)
        return {'market':m,'ts_ms':ts,'type':'book_v3',**self._book_features(m,ts)}

    def _tx(self,m,c): return [x for x in self.trades[m] if int(x.get('trade_ts_ms') or x['recv_ms'])>=c]
    def _flow(self,xs,n):
        if not xs:return {f'notional_{n}':0,f'delta_{n}':0,f'efficiency_{n}':None}
        buy=sum(float(x['notional']) for x in xs if x['side']=='BID'); sell=sum(float(x['notional']) for x in xs if x['side']=='ASK')
        p0=float(xs[0]['price']); p1=float(xs[-1]['price']); ret=p1/p0-1 if p0 else 0; total=buy+sell
        # Price efficiency: absolute price response per 100m KRW turnover. Low = lots of activity, restrained price.
        eff=abs(ret)/(total/1e8) if total else None
        return {f'notional_{n}':total,f'delta_{n}':buy-sell,f'delta_ratio_{n}':(buy-sell)/total if total else 0,
                f'ret_{n}':ret,f'efficiency_{n}':eff}
    def _divergence(self,xs):
        if len(xs)<10:return {'bull_cvd_div':False,'bear_cvd_div':False}
        mid=len(xs)//2; a,b=xs[:mid],xs[mid:]
        def d(z):return sum(float(x['notional'])*(1 if x['side']=='BID' else -1) for x in z)
        pa,pb=float(a[-1]['price']),float(b[-1]['price']); pr=pb/pa-1 if pa else 0; dd=d(b)-d(a)
        return {'cvd_delta_change_5m':dd,'price_change_halves_5m':pr,'bull_cvd_div':dd>0 and pr<=0,'bear_cvd_div':dd<0 and pr>=0}
    def _persistent_absorption(self,m,ts):
        flags=[]
        for k in range(5):
            xs=[x for x in self.trades[m] if ts-(k+1)*60000<int(x.get('trade_ts_ms') or x['recv_ms'])<=ts-k*60000]
            if not xs:continue
            buy=sum(float(x['notional']) for x in xs if x['side']=='BID'); sell=sum(float(x['notional']) for x in xs if x['side']=='ASK'); total=buy+sell
            r=float(xs[-1]['price'])/float(xs[0]['price'])-1 if float(xs[0]['price']) else 0; im=(buy-sell)/total if total else 0
            flags.append((im<=-.25 and r>-.0025,im>=.25 and r<.0025))
        return {'down_absorb_minutes_5m':sum(a for a,_ in flags),'up_absorb_minutes_5m':sum(b for _,b in flags)}
    def _sweep(self,m,ts):
        xs=self._tx(m,ts-10000)
        if len(xs)<3:return {'bid_sweep':False,'ask_sweep':False}
        bids=[x for x in xs if x['side']=='BID']; asks=[x for x in xs if x['side']=='ASK']
        return {'bid_sweep':len(bids)>=3 and len({float(x['price']) for x in bids})>=3,
                'ask_sweep':len(asks)>=3 and len({float(x['price']) for x in asks})>=3}
    def _relative_flow(self,m,ts,xs):
        coin=sum(float(x['notional']) for x in xs); market=sum(n for t,n in self.market_notional if t>=ts-300000)
        return {'market_relative_flow_5m':coin/market if market else 0}
    def _book_features(self,m,ts):
        xs=[x for x in self.books[m] if x['ts']>=ts-60000]
        if len(xs)<3:return {'valid':True,'bid_refill':False,'ask_refill':False,'iceberg_bid_suspect':False,'iceberg_ask_suspect':False,'liquidity_vacuum_up':False}
        last=xs[-1]; bmin=min(x['bid_size'] for x in xs); amin=min(x['ask_size'] for x in xs)
        br=last['bid_size']/bmin if bmin else 1; ar=last['ask_size']/amin if amin else 1
        # Repeated depletion+rebuild is only an iceberg suspicion proxy, never proof.
        bid_ref=sum(1 for i in range(1,len(xs)) if xs[i-1]['bid_size']>xs[i]['bid_size'] and xs[i]['bid_size']<last['bid_size'])
        ask_ref=sum(1 for i in range(1,len(xs)) if xs[i-1]['ask_size']>xs[i]['ask_size'] and xs[i]['ask_size']<last['ask_size'])
        asks=[float(u['ask_size']) for u in last['levels'] if u.get('ask_size') is not None]
        near=sum(asks[:5]); deep=sum(asks[5:15]); vacuum=bool(deep and near/deep<.25)
        return {'valid':True,'bid_refill_ratio_60s':br,'ask_refill_ratio_60s':ar,'bid_refill':br>=1.5,'ask_refill':ar>=1.5,
                'iceberg_bid_suspect':bid_ref>=3 and br>=1.25,'iceberg_ask_suspect':ask_ref>=3 and ar>=1.25,
                'liquidity_vacuum_up':vacuum,'book_imbalance':(last['tb']-last['ta'])/(last['tb']+last['ta']) if last['tb']+last['ta'] else 0}
