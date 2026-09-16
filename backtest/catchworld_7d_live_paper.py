import csv, json, os, time, requests
from datetime import datetime, timezone

OUT=os.getenv('OUT','catchworld_7d_paper.csv')
RUN_MINUTES=int(os.getenv('RUN_MINUTES','55'))
FLOW_MIN=float(os.getenv('FLOW_MIN','6'))
PB_LO=float(os.getenv('PB_LO','-0.025')); PB_HI=float(os.getenv('PB_HI','-0.020'))
API='https://api.upbit.com/v1'
FIELDS=['time','market','strategy','state','price','flow','ret30','turnover5','base72','note']

def markets():
    r=requests.get(API+'/market/all',params={'is_details':'false'},timeout=20); r.raise_for_status()
    return [x['market'] for x in r.json() if x['market'].startswith('KRW-')]

def candles(m,count=80):
    r=requests.get(API+'/candles/minutes/5',params={'market':m,'count':count},timeout=15)
    if r.status_code!=200:return []
    return list(reversed(r.json()))

def med(v):
    s=sorted(v); n=len(s)
    return s[n//2] if n%2 else (s[n//2-1]+s[n//2])/2

def snapshot(m):
    c=candles(m)
    if len(c)<73:return None
    turns=[float(x.get('candle_acc_trade_price') or 0) for x in c]
    prices=[float(x['trade_price']) for x in c]
    base=med(turns[-73:-1]); flow=turns[-1]/base if base else 0
    ret30=prices[-1]/prices[-7]-1 if prices[-7] else 0
    return prices[-1],flow,ret30,turns[-1],base

def main():
    ms=markets(); new=not os.path.exists(OUT); seen={}
    with open(OUT,'a',newline='',encoding='utf-8') as f:
        w=csv.DictWriter(f,fieldnames=FIELDS)
        if new:w.writeheader()
        end=time.time()+RUN_MINUTES*60
        while time.time()<end:
            for m in ms:
                try:
                    s=snapshot(m)
                    if not s:continue
                    p,flow,r30,t5,b=s
                    eligible=flow>=FLOW_MIN and PB_LO<=r30<=PB_HI
                    if eligible:
                        bucket=int(time.time()//300)
                        if seen.get(m)!=bucket:
                            seen[m]=bucket
                            now=datetime.now(timezone.utc).isoformat()
                            for strat in ('A_FLOW_PULLBACK','B_TRADE_PENDING','C_MICRO_PENDING'):
                                w.writerow({'time':now,'market':m,'strategy':strat,'state':'ELIGIBLE','price':p,'flow':flow,'ret30':r30,'turnover5':t5,'base72':b,'note':'B/C require synchronized trade/orderbook evidence'})
                            f.flush()
                    time.sleep(0.08)
                except Exception as e:
                    continue
            time.sleep(5)

if __name__=='__main__':main()
