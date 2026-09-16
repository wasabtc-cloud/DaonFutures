"""CatchWorld synchronized Upbit microstructure collector + V4 research sensors.
No BUY/SELL decisions. Persistent host recommended; not an indefinite GitHub Action.
"""
from __future__ import annotations
import asyncio,json,os,time
from collections import defaultdict
from datetime import datetime,timezone
from pathlib import Path
from typing import Any
import aiohttp
try: from collector.microstructure_engine_v4 import MicrostructureEngineV4
except ImportError: from microstructure_engine_v4 import MicrostructureEngineV4
WS_URL='wss://api.upbit.com/websocket/v1';REST='https://api.upbit.com/v1/market/all';OUT=Path(os.getenv('CW_MICRO_OUT','data/microstructure'));OUT.mkdir(parents=True,exist_ok=True)
sensor=MicrostructureEngineV4();cvd=defaultdict(float);last_book=defaultdict(int);BOOK_MS=int(os.getenv('CW_BOOK_WRITE_MS','500'))
def hour():return datetime.now(timezone.utc).strftime('%Y%m%d_%H')
def append(kind,row):
 d=OUT/kind;d.mkdir(parents=True,exist_ok=True)
 with (d/f'{hour()}.jsonl').open('a',encoding='utf-8') as f:f.write(json.dumps(row,ensure_ascii=False,separators=(',',':'))+'\n')
async def markets(s):
 async with s.get(REST,params={'isDetails':'false'},timeout=20) as r:r.raise_for_status();z=await r.json()
 return sorted(x['market'] for x in z if x['market'].startswith('KRW-'))
def trade_row(m):
 p=float(m['trade_price']);v=float(m['trade_volume']);side=str(m.get('ask_bid',''));signed=p*v*(1 if side=='BID' else -1);mk=m['code'];cvd[mk]+=signed
 return {'recv_ms':int(time.time()*1000),'market':mk,'trade_ts_ms':m.get('trade_timestamp'),'sequential_id':m.get('sequential_id'),'price':p,'volume':v,'notional':p*v,'side':side,'signed_notional':signed,'cvd_notional':cvd[mk]}
def book_row(m):
 u=m.get('orderbook_units',[]);return {'recv_ms':int(time.time()*1000),'market':m['code'],'timestamp':m.get('timestamp'),'total_ask_size':m.get('total_ask_size'),'total_bid_size':m.get('total_bid_size'),'levels':[{'ask_price':x.get('ask_price'),'bid_price':x.get('bid_price'),'ask_size':x.get('ask_size'),'bid_size':x.get('bid_size')} for x in u[:15]]}
async def consume(ms):
 chunks=[ms[i:i+80] for i in range(0,len(ms),80)]
 async def worker(codes,idx):
  while True:
   try:
    async with aiohttp.ClientSession() as s:
     async with s.ws_connect(WS_URL,heartbeat=30,receive_timeout=90) as ws:
      await ws.send_str(json.dumps([{'ticket':f'catchworld-v4-{idx}'},{'type':'trade','codes':codes,'is_only_realtime':True},{'type':'orderbook','codes':codes,'is_only_realtime':True},{'format':'DEFAULT'}]))
      async for msg in ws:
       if msg.type==aiohttp.WSMsgType.BINARY:m=json.loads(msg.data.decode())
       elif msg.type==aiohttp.WSMsgType.TEXT:m=json.loads(msg.data)
       else:continue
       if m.get('type')=='trade':
        r=trade_row(m);append('trades',r);append('sensors',sensor.on_trade(r))
       elif m.get('type')=='orderbook':
        r=book_row(m);append('book_sensors',sensor.on_book(r));now=r['recv_ms']
        # Sensor receives every update; raw books are throttled to control storage.
        if now-last_book[r['market']]>=BOOK_MS:append('orderbook',r);last_book[r['market']]=now
   except Exception as e:append('system',{'ts_ms':int(time.time()*1000),'worker':idx,'error':repr(e)});await asyncio.sleep(5)
 await asyncio.gather(*(worker(c,i) for i,c in enumerate(chunks)))
async def main():
 async with aiohttp.ClientSession() as s:ms=await markets(s)
 append('system',{'ts_ms':int(time.time()*1000),'event':'start_v4','markets':len(ms),'raw_book_interval_ms':BOOK_MS});await consume(ms)
if __name__=='__main__':asyncio.run(main())
