import math, time, requests
from datetime import datetime, timezone, timedelta
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt

START_CAPITAL=1_000_000.0
TARGET=100_000_000.0
FEE=0.0005
SLIP=0.0003
COST=FEE+SLIP
TOP_LIQUID=60
DAYS=365
WARMUP=90
BASE='https://api.upbit.com/v1'


def get_json(path, params=None):
    r=requests.get(BASE+path, params=params, timeout=20, headers={'User-Agent':'DaonFutures-100X'})
    r.raise_for_status()
    time.sleep(0.11)
    return r.json()


def fetch_days(market, start, end):
    rows=[]; to=end
    while to>start:
        js=get_json('/candles/days', {'market':market,'count':200,'to':to.strftime('%Y-%m-%dT%H:%M:%SZ')})
        if not js: break
        rows.extend(js)
        oldest=pd.Timestamp(js[-1]['candle_date_time_utc'], tz='UTC')
        if oldest<=start: break
        to=oldest-pd.Timedelta(seconds=1)
    if not rows: return pd.DataFrame()
    d=pd.DataFrame(rows)
    d['time']=pd.to_datetime(d['candle_date_time_utc'], utc=True)
    d=d.drop_duplicates('time').set_index('time').sort_index()
    out=pd.DataFrame(index=d.index)
    out['open']=pd.to_numeric(d['opening_price'])
    out['high']=pd.to_numeric(d['high_price'])
    out['low']=pd.to_numeric(d['low_price'])
    out['close']=pd.to_numeric(d['trade_price'])
    out['value']=pd.to_numeric(d['candle_acc_trade_price'])
    return out.loc[(out.index>=start)&(out.index<=end)]


def load_data():
    end=pd.Timestamp(datetime.now(timezone.utc)).floor('D')
    start=end-pd.Timedelta(days=DAYS)
    warm=start-pd.Timedelta(days=WARMUP)
    markets=get_json('/market/all', {'is_details':'false'})
    krw=[x['market'] for x in markets if x['market'].startswith('KRW-')]
    tickers=[]
    for i in range(0,len(krw),100):
        tickers.extend(get_json('/ticker', {'markets':','.join(krw[i:i+100])}))
    liq=sorted(tickers,key=lambda x:float(x.get('acc_trade_price_24h',0)),reverse=True)
    chosen=[x['market'] for x in liq[:TOP_LIQUID]]
    if 'KRW-BTC' not in chosen: chosen.append('KRW-BTC')
    data={}
    for n,m in enumerate(chosen,1):
        try:
            d=fetch_days(m,warm,end)
            if len(d)>=120: data[m]=features(d)
        except Exception as e:
            print('skip',m,e,flush=True)
        print('download',n,'/',len(chosen),m,flush=True)
    return data,start,end


def features(d):
    d=d.copy()
    d['mom3']=d.close.pct_change(3)
    d['mom7']=d.close.pct_change(7)
    d['mom14']=d.close.pct_change(14)
    d['mom30']=d.close.pct_change(30)
    d['mom60']=d.close.pct_change(60)
    d['vol20']=d.close.pct_change().rolling(20).std()
    d['sma50']=d.close.rolling(50).mean()
    d['sma100']=d.close.rolling(100).mean()
    d['hh20']=d.high.shift(1).rolling(20).max()
    d['hh50']=d.high.shift(1).rolling(50).max()
    d['value20']=d.value.rolling(20).mean()
    d['value_ratio']=d.value/d.value20
    return d


def score_row(name, row):
    if name=='MOM7': return row.mom7
    if name=='MOM30': return row.mom30
    if name=='DUAL': return 0.6*row.mom7+0.4*row.mom30
    if name=='ACCEL': return row.mom3+0.7*row.mom7
    if name=='BREAK20': return (row.close/row.hh20-1) if row.close>row.hh20 else np.nan
    if name=='BREAK50': return (row.close/row.hh50-1) if row.close>row.hh50 else np.nan
    if name=='FLOWMOM': return row.mom7*max(row.value_ratio,0)
    if name=='LOWVOLMOM': return row.mom30/(row.vol20+1e-6)
    return np.nan


def regime_ok(mode, btcrow):
    if mode=='ALL': return True
    if mode=='BTC50': return bool(btcrow.close>btcrow.sma50)
    if mode=='BTC100': return bool(btcrow.close>btcrow.sma100)
    return True


def run_combo(data, dates, strategy, topk, hold, regime):
    btc=data.get('KRW-BTC')
    if btc is None: return None
    eq=START_CAPITAL; peak=eq; mdd=0.0; trades=0; wins=0; gross_win=0.0; gross_loss=0.0
    curve=[]; i=0
    while i+hold+1 < len(dates):
        sig=dates[i]; entry_t=dates[i+1]; exit_t=dates[i+1+hold]
        if sig not in btc.index or entry_t not in btc.index:
            i+=hold; continue
        if not regime_ok(regime,btc.loc[sig]):
            curve.append((exit_t,eq)); i+=hold; continue
        ranked=[]
        for m,d in data.items():
            if m=='KRW-BTC' or sig not in d.index or entry_t not in d.index or exit_t not in d.index: continue
            r=d.loc[sig]
            s=score_row(strategy,r)
            if not np.isfinite(s) or s<=0: continue
            if r.value < 500_000_000: continue
            ranked.append((float(s),m))
        ranked.sort(reverse=True)
        picks=ranked[:topk]
        if not picks:
            curve.append((exit_t,eq)); i+=hold; continue
        rets=[]
        for _,m in picks:
            d=data[m]
            en=float(d.loc[entry_t,'open'])*(1+COST)
            ex=float(d.loc[exit_t,'open'])*(1-COST)
            ret=ex/en-1
            if np.isfinite(ret): rets.append(ret)
        if rets:
            pr=float(np.mean(rets)); eq*=max(0.0,1+pr); trades+=len(rets)
            if pr>0: wins+=1; gross_win+=pr
            else: gross_loss+=-pr
            peak=max(peak,eq); mdd=max(mdd,(peak-eq)/peak if peak else 1)
            curve.append((exit_t,eq))
        i+=hold
    pf=(gross_win/gross_loss) if gross_loss>0 else (999.0 if gross_win>0 else 0.0)
    return {'strategy':strategy,'topk':topk,'hold_days':hold,'regime':regime,'final_capital_krw':eq,
            'return_pct':(eq/START_CAPITAL-1)*100,'target_hit':eq>=TARGET,'rebalance_wins':wins,'trades':trades,
            'profit_factor':pf,'max_drawdown_pct':mdd*100,'curve':curve}


def main():
    data,start,end=load_data()
    all_dates=sorted(set.intersection(*[set(d.index) for d in data.values() if len(d)>0])) if data else []
    all_dates=[x for x in all_dates if x>=start and x<=end]
    strategies=['MOM7','MOM30','DUAL','ACCEL','BREAK20','BREAK50','FLOWMOM','LOWVOLMOM']
    rows=[]; curves={}
    total=len(strategies)*4*6*3; c=0
    for s in strategies:
      for k in [1,2,3,5]:
       for h in [1,2,3,5,7,14]:
        for rg in ['ALL','BTC50','BTC100']:
            c+=1
            z=run_combo(data,all_dates,s,k,h,rg)
            if z:
                curves[(s,k,h,rg)]=z.pop('curve'); rows.append(z)
            if c%50==0: print('tested',c,'/',total,flush=True)
    res=pd.DataFrame(rows).sort_values(['final_capital_krw','profit_factor'],ascending=False)
    res.to_csv('backtest_results.csv',index=False)
    plt.figure(figsize=(12,6))
    for _,r in res.head(5).iterrows():
        key=(r.strategy,int(r.topk),int(r.hold_days),r.regime); cv=curves.get(key,[])
        if cv:
            x=[a for a,b in cv]; y=[b for a,b in cv]; plt.plot(x,y,label=f'{key[0]} K{key[1]} H{key[2]} {key[3]}')
    plt.axhline(TARGET,linestyle='--',linewidth=1)
    plt.yscale('log'); plt.ylabel('KRW (log)'); plt.xlabel('Time'); plt.title('Upbit 100X Strategy Search - Top 5'); plt.legend(); plt.tight_layout(); plt.savefig('backtest_equity.png',dpi=150)
    print(res.head(20).to_string(index=False),flush=True)
    print('TARGET_HITS',int(res.target_hit.sum()),'BEST',float(res.iloc[0].final_capital_krw),flush=True)

if __name__=='__main__': main()
