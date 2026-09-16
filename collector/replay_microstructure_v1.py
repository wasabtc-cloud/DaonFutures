"""Replay raw CatchWorld JSONL deterministically through V4 sensors.
Usage: python collector/replay_microstructure_v1.py data/microstructure/trades/*.jsonl data/microstructure/orderbook/*.jsonl
"""
import json,sys
from pathlib import Path
try: from collector.microstructure_engine_v4 import MicrostructureEngineV4
except ImportError: from microstructure_engine_v4 import MicrostructureEngineV4
def rows(paths):
 z=[]
 for p in paths:
  for line in Path(p).open(encoding='utf-8'):
   try:
    x=json.loads(line);ts=int(x.get('trade_ts_ms') or x.get('timestamp') or x.get('recv_ms') or 0);z.append((ts,x))
   except:pass
 return sorted(z,key=lambda a:a[0])
def main(paths):
 e=MicrostructureEngineV4();ntr=nb=0
 for _,x in rows(paths):
  if 'side' in x and 'notional' in x:e.on_trade(x);ntr+=1
  elif 'levels' in x:e.on_book(x);nb+=1
 print(json.dumps({'trades_replayed':ntr,'books_replayed':nb,'status':'ok'}))
if __name__=='__main__':main(sys.argv[1:])
