import os, time, requests, pandas as pd, numpy as np
from datetime import datetime, timezone

BASE='https://api.upbit.com/v1'
SHARD=int(os.getenv('SHARD','0')); SHARDS=int(os.getenv('SHARDS','8'))
SLEEP=float(os.getenv('SLEEP','0.12'))

def get_json(url, params=None, retries=8):
    for i in range(retries):
        r=requests.get(url,params=params,timeout=20)
        if r.status_code==200: return r.json()
        if r.status_code==429:
            time.sleep(max(0.5,0.5*(i+1))); continue
        r.raise_for_status()
    raise RuntimeError('request failed')

markets=sorted([x['market'] for x in get_json(BASE+'/market/all',{'is_details':'false'}) if x['market'].startswith('KRW-')])
markets=[m for i,m in enumerate(markets) if i%SHARDS==SHARD]
rows=[]

for mi,m in enumerate(markets,1):
    for days_ago in range(1,8):
        cursor=None
        seen=set()
        while True:
            p={'market':m,'count':500,'days_ago':days_ago}
            if cursor is not None: p['cursor']=cursor
            data=get_json(BASE+'/trades/ticks',p)
            if not data: break
            new=0
            for x in data:
                sid=int(x['sequential_id'])
                if sid in seen: continue
                seen.add(sid); new+=1
                rows.append({
                    'market':m,
                    'timestamp':int(x['timestamp']),
                    'trade_price':float(x['trade_price']),
                    'trade_volume':float(x['trade_volume']),
                    'trade_value':float(x['trade_price'])*float(x['trade_volume']),
                    'ask_bid':x['ask_bid'],
                    'sequential_id':sid,
                    'days_ago':days_ago,
                })
            if len(data)<500 or new==0: break
            nxt=min(int(x['sequential_id']) for x in data)
            if cursor==nxt: break
            cursor=nxt
            time.sleep(SLEEP)
        print(f'{mi}/{len(markets)} {m} day={days_ago} rows={len(rows)}',flush=True)

raw=pd.DataFrame(rows)
if raw.empty:
    pd.DataFrame().to_csv(f'trade_strength_7d_raw_shard_{SHARD}.csv',index=False)
    pd.DataFrame().to_csv(f'trade_strength_7d_1m_shard_{SHARD}.csv',index=False)
else:
    raw=raw.drop_duplicates(['market','sequential_id']).sort_values(['market','timestamp'])
    raw['time']=pd.to_datetime(raw.timestamp,unit='ms',utc=True)
    raw.to_csv(f'trade_strength_7d_raw_shard_{SHARD}.csv',index=False)
    d=raw.copy()
    d['minute']=d.time.dt.floor('min')
    d['bid_value']=np.where(d.ask_bid.eq('BID'),d.trade_value,0.0)
    d['ask_value']=np.where(d.ask_bid.eq('ASK'),d.trade_value,0.0)
    d['bid_volume']=np.where(d.ask_bid.eq('BID'),d.trade_volume,0.0)
    d['ask_volume']=np.where(d.ask_bid.eq('ASK'),d.trade_volume,0.0)
    g=d.groupby(['market','minute'],as_index=False).agg(
        bid_value=('bid_value','sum'), ask_value=('ask_value','sum'),
        bid_volume=('bid_volume','sum'), ask_volume=('ask_volume','sum'),
        trades=('sequential_id','count'), last_price=('trade_price','last'))
    g['strength_value']=np.where(g.ask_value>0,100*g.bid_value/g.ask_value,np.nan)
    g['strength_volume']=np.where(g.ask_volume>0,100*g.bid_volume/g.ask_volume,np.nan)
    g['net_aggressive_value']=g.bid_value-g.ask_value
    g.to_csv(f'trade_strength_7d_1m_shard_{SHARD}.csv',index=False)
print('done',SHARD,len(raw) if not raw.empty else 0,flush=True)
