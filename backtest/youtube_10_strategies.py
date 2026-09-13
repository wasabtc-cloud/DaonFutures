import time, requests
from datetime import datetime, timezone
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt

START=1_000_000.0
TARGET=100_000_000.0
FEE=0.0005
SLIP=0.0003
COST=FEE+SLIP
DAYS=365
WARMUP=120
TOP_LIQUID=60
BASE='https://api.upbit.com/v1'


def get_json(path, params=None):
    r=requests.get(BASE+path,params=params,timeout=20,headers={'User-Agent':'DaonFutures-Feasibility'})
    r.raise_for_status(); time.sleep(0.11); return r.json()


def fetch_days(market,start,end):
    rows=[]; to=end
    while to>start:
        js=get_json('/candles/days',{'market':market,'count':200,'to':to.strftime('%Y-%m-%dT%H:%M:%SZ')})
        if not js: break
        rows.extend(js)
        oldest=pd.Timestamp(js[-1]['candle_date_time_utc'],tz='UTC')
        if oldest<=start: break
        to=oldest-pd.Timedelta(seconds=1)
    if not rows: return pd.DataFrame()
    d=pd.DataFrame(rows); d['time']=pd.to_datetime(d['candle_date_time_utc'],utc=True)
    d=d.drop_duplicates('time').set_index('time').sort_index()
    out=pd.DataFrame(index=d.index)
    for src,dst in [('opening_price','open'),('trade_price','close'),('candle_acc_trade_price','value')]: out[dst]=pd.to_numeric(d[src])
    out['mom3']=out.close.pct_change(3); out['mom7']=out.close.pct_change(7); out['mom14']=out.close.pct_change(14); out['mom30']=out.close.pct_change(30)
    out['sma50']=out.close.rolling(50).mean(); out['value20']=out.value.rolling(20).mean(); out['value_ratio']=out.value/out.value20
    return out.loc[(out.index>=start)&(out.index<=end)]


def load():
    end=pd.Timestamp(datetime.now(timezone.utc)).floor('D'); start=end-pd.Timedelta(days=DAYS); warm=start-pd.Timedelta(days=WARMUP)
    markets=get_json('/market/all',{'is_details':'false'}); krw=[x['market'] for x in markets if x['market'].startswith('KRW-')]
    ticks=[]
    for i in range(0,len(krw),100): ticks += get_json('/ticker',{'markets':','.join(krw[i:i+100])})
    chosen=[x['market'] for x in sorted(ticks,key=lambda x:float(x.get('acc_trade_price_24h',0)),reverse=True)[:TOP_LIQUID]]
    if 'KRW-BTC' not in chosen: chosen.append('KRW-BTC')
    data={}
    for n,m in enumerate(chosen,1):
        try:
            d=fetch_days(m,warm,end)
            if len(d)>=150: data[m]=d
        except Exception as e: print('skip',m,e,flush=True)
        print('download',n,'/',len(chosen),m,flush=True)
    return data,start,end


def netret(d,t0,t1):
    en=float(d.loc[t0,'open'])*(1+COST); ex=float(d.loc[t1,'open'])*(1-COST); return ex/en-1


def eligibility(data,t):
    arr=[]
    for m,d in data.items():
        if t in d.index and np.isfinite(d.loc[t,'value']) and d.loc[t,'value']>=500_000_000: arr.append(m)
    return arr


def oracle(data,dates,liquidity_top=None):
    eq=START; peak=eq; mdd=0; trades=0; curve=[]; hit_date=None
    for i in range(len(dates)-1):
        s,e=dates[i],dates[i+1]; elig=eligibility(data,s)
        if liquidity_top:
            elig=sorted(elig,key=lambda m:float(data[m].loc[s,'value']),reverse=True)[:liquidity_top]
        best=0.0; bestm='CASH'
        for m in elig:
            d=data[m]
            if e not in d.index: continue
            r=netret(d,s,e)
            if np.isfinite(r) and r>best: best=r; bestm=m
        if best>0:
            eq*=1+best; trades+=1
        peak=max(peak,eq); mdd=max(mdd,(peak-eq)/peak if peak else 0); curve.append((e,eq,bestm,best))
        if hit_date is None and eq>=TARGET: hit_date=e
    return eq,mdd*100,trades,curve,hit_date


def causal(data,dates,score_name,topk=1):
    eq=START; peak=eq; mdd=0; trades=0; curve=[]; hit_date=None
    btc=data.get('KRW-BTC')
    for i in range(len(dates)-1):
        s,e=dates[i],dates[i+1]
        if btc is None or s not in btc.index or not np.isfinite(btc.loc[s,'sma50']) or btc.loc[s,'close']<=btc.loc[s,'sma50']:
            curve.append((e,eq,'CASH',0.0)); continue
        ranked=[]
        for m in eligibility(data,s):
            if m=='KRW-BTC': continue
            d=data[m]
            if e not in d.index: continue
            r=d.loc[s]
            if score_name=='MOM7': sc=r.mom7
            elif score_name=='MOM30': sc=r.mom30
            elif score_name=='ACCEL': sc=r.mom3+0.7*r.mom7
            elif score_name=='FLOW': sc=r.mom7*r.value_ratio
            else: sc=np.nan
            if np.isfinite(sc) and sc>0: ranked.append((float(sc),m))
        ranked.sort(reverse=True); picks=[m for _,m in ranked[:topk]]
        if picks:
            rs=[netret(data[m],s,e) for m in picks]; rs=[r for r in rs if np.isfinite(r)]
            if rs:
                pr=float(np.mean(rs)); eq*=max(0,1+pr); trades+=len(rs)
        peak=max(peak,eq); mdd=max(mdd,(peak-eq)/peak if peak else 0); curve.append((e,eq,','.join(picks) if picks else 'CASH',0.0))
        if hit_date is None and eq>=TARGET: hit_date=e
    return eq,mdd*100,trades,curve,hit_date


def main():
    data,start,end=load()
    dates=sorted(set().union(*[set(d.index) for d in data.values()]))
    dates=[x for x in dates if start<=x<=end]
    tests=[]; curves={}
    for label,lt in [('ORACLE_ALL',None),('ORACLE_TOP20_LIQ',20),('ORACLE_TOP10_LIQ',10),('ORACLE_TOP5_LIQ',5)]:
        eq,mdd,tr,cv,hit=oracle(data,dates,lt); tests.append((label,eq,mdd,tr,hit)); curves[label]=cv
    for score in ['MOM7','MOM30','ACCEL','FLOW']:
        for k in [1,3,5]:
            label=f'CAUSAL_{score}_TOP{k}_BTC50'; eq,mdd,tr,cv,hit=causal(data,dates,score,k); tests.append((label,eq,mdd,tr,hit)); curves[label]=cv
    rows=[]
    for label,eq,mdd,tr,hit in tests:
        rows.append({'test':label,'start_capital_krw':START,'final_capital_krw':eq,'return_pct':(eq/START-1)*100,'target_100m_hit':eq>=TARGET,'target_hit_date':str(hit) if hit is not None else '', 'trades':tr,'max_drawdown_pct':mdd})
    res=pd.DataFrame(rows).sort_values('final_capital_krw',ascending=False); res.to_csv('backtest_results.csv',index=False)
    plt.figure(figsize=(12,6))
    for label in ['ORACLE_TOP10_LIQ','ORACLE_TOP5_LIQ']:
        cv=curves[label]; plt.plot([x[0] for x in cv],[x[1] for x in cv],label=label)
    best_causal=res[res.test.str.startswith('CAUSAL_')].iloc[0].test
    cv=curves[best_causal]; plt.plot([x[0] for x in cv],[x[1] for x in cv],label=best_causal)
    plt.axhline(TARGET,linestyle='--',linewidth=1,label='100M target'); plt.yscale('log'); plt.ylabel('KRW (log)'); plt.xlabel('Time'); plt.title('Upbit 100X Feasibility: Oracle Upper Bound vs Causal'); plt.legend(); plt.tight_layout(); plt.savefig('backtest_equity.png',dpi=150)
    print(res.to_string(index=False),flush=True)
    print('IMPORTANT: ORACLE rows deliberately use next-day return to measure an upper bound, not a tradable strategy.',flush=True)
    print('CAUSAL rows use only information known by signal day, but current-listing universe still has survivorship bias.',flush=True)

if __name__=='__main__': main()
