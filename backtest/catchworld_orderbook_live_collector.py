import asyncio, json, csv, os
from datetime import datetime, timezone
import requests, websockets

OUT=os.getenv('OUT','orderbook_live.csv')
MINUTES=int(os.getenv('MINUTES','60'))

markets=[x['market'] for x in requests.get('https://api.upbit.com/v1/market/all',params={'is_details':'false'},timeout=20).json() if x['market'].startswith('KRW-')]
fields=['time','market','total_ask_size','total_bid_size','imbalance','best_ask_price','best_bid_price','best_ask_size','best_bid_size','spread_pct']

async def main():
    uri='wss://api.upbit.com/websocket/v1'
    end=asyncio.get_event_loop().time()+MINUTES*60
    new=not os.path.exists(OUT)
    with open(OUT,'a',newline='',encoding='utf-8') as f:
        w=csv.DictWriter(f,fieldnames=fields)
        if new:w.writeheader()
        async with websockets.connect(uri,ping_interval=20,max_size=None) as ws:
            await ws.send(json.dumps([{'ticket':'catchworld-orderbook'},{'type':'orderbook','codes':markets,'is_only_realtime':True},{'format':'DEFAULT'}]))
            while asyncio.get_event_loop().time()<end:
                d=json.loads(await asyncio.wait_for(ws.recv(),timeout=30))
                u=d.get('orderbook_units') or []
                if not u: continue
                ask=float(d.get('total_ask_size') or 0); bid=float(d.get('total_bid_size') or 0)
                den=ask+bid; imb=(bid-ask)/den if den else 0
                ba=float(u[0].get('ask_price') or 0); bb=float(u[0].get('bid_price') or 0)
                mid=(ba+bb)/2 if ba and bb else 0
                w.writerow({'time':datetime.now(timezone.utc).isoformat(),'market':d.get('code'),'total_ask_size':ask,'total_bid_size':bid,'imbalance':imb,'best_ask_price':ba,'best_bid_price':bb,'best_ask_size':u[0].get('ask_size'),'best_bid_size':u[0].get('bid_size'),'spread_pct':((ba-bb)/mid if mid else 0)})
                f.flush()

asyncio.run(main())
