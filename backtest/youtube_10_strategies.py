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
WARMUP=220
BASE='https://api.upbit.com/v1'


def get_json(path, params=None):
    r=requests.get(BASE+path,params=params,timeout=20,headers={'User-Agent':'DaonFutures-Audit'})
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
    for src,dst in [('opening_price','open'),('trade_price','close'),('candle_acc_trade_price','value')]:
        out[dst]=pd.to_numeric(d[src])
    out['ret1']=out.close.pct_change()
    out['mom3']=out.close.pct_change(3); out['mom7']=out.close.pct_change(7); out['mom30']=out.close.pct_change(30)
    out['sma50']=out.close.rolling(50).mean(); out['sma100']=out.close.rolling(100).mean()
    out['value20']=out.value.rolling(20).mean(); out['value_ratio']=out.value/out.value20
    out['age_bars']=np.arange(1,len(out)+1)
    return out.loc[(out.index>=start)&(out.index<=end)]


def load():
    end=pd.Timestamp(datetime.now(timezone.utc)).floor('D'); test_start=end-pd.Timedelta(days=DAYS); warm=test_start-pd.Timedelta(days=WARMUP)
    markets=get_json('/market/all',{'is_details':'false'})
    chosen=[x['market'] for x in markets if x['market'].startswith('KRW-')]
    data={}
    for n,m in enumerate(chosen,1):
        try:
            d=fetch_days(m,warm,end)
            if len(d)>=80: data[m]=d
        except Exception as e: print('skip',m,e,flush=True)
        if n%25==0 or n==len(chosen): print('download',n,'/',len(chosen),flush=True)
    return data,test_start,end


def tradable_row(d,t):
    if t not in d.index: return False
    r=d.loc[t]
    # Require real history before signal and meaningful liquidity before selection.
    return bool(r.age_bars>=120 and np.isfinite(r.value20) and r.value20>=1_000_000_000 and r.value>=500_000_000)


def score(r,name):
    if name=='MOM7': return r.mom7
    if name=='MOM30': return r.mom30
    if name=='ACCEL': return r.mom3+0.7*r.mom7
    if name=='FLOW': return r.mom7*r.value_ratio
    return np.nan


def next_open_return(d,entry_t,exit_t):
    if entry_t not in d.index or exit_t not in d.index: return np.nan
    en=float(d.loc[entry_t,'open'])*(1+COST)
    ex=float(d.loc[exit_t,'open'])*(1-COST)
    return ex/en-1


def causal(data,dates,score_name,topk=1,regime='BTC50'):
    eq=START; peak=eq; mdd=0.0; trades=0; hit_date=None; curve=[]; audit=[]
    btc=data.get('KRW-BTC')
    # IMPORTANT: signal is day i close, entry is day i+1 open, exit is day i+2 open.
    for i in range(len(dates)-2):
        sig,entry_t,exit_t=dates[i],dates[i+1],dates[i+2]
        if btc is None or sig not in btc.index: continue
        br=btc.loc[sig]
        if regime=='BTC50' and (not np.isfinite(br.sma50) or br.close<=br.sma50):
            curve.append((exit_t,eq)); continue
        if regime=='BTC100' and (not np.isfinite(br.sma100) or br.close<=br.sma100):
            curve.append((exit_t,eq)); continue
        ranked=[]
        for m,d in data.items():
            if m=='KRW-BTC' or not tradable_row(d,sig): continue
            if entry_t not in d.index or exit_t not in d.index: continue
            r=d.loc[sig]; sc=score(r,score_name)
            if not np.isfinite(sc) or sc<=0: continue
            # Avoid one-day listing/pump artifacts in the signal itself.
            if np.isfinite(r.ret1) and r.ret1>0.30: continue
            ranked.append((float(sc),m))
        ranked.sort(reverse=True); picks=[m for _,m in ranked[:topk]]
        if not picks:
            curve.append((exit_t,eq)); continue
        rs=[]
        for m in picks:
            rr=next_open_return(data[m],entry_t,exit_t)
            if np.isfinite(rr): rs.append((m,rr))
        if not rs:
            curve.append((exit_t,eq)); continue
        pr=float(np.mean([x[1] for x in rs])); before=eq; eq*=max(0.0,1+pr); trades+=len(rs)
        peak=max(peak,eq); mdd=max(mdd,(peak-eq)/peak if peak else 0)
        audit.append({'signal_date':sig,'entry_date':entry_t,'exit_date':exit_t,'strategy':score_name,'topk':topk,
                      'coins':','.join([x[0] for x in rs]),'portfolio_return_pct':pr*100,'equity_before':before,'equity_after':eq})
        curve.append((exit_t,eq))
        if hit_date is None and eq>=TARGET: hit_date=exit_t
    return {'test':f'AUDIT_{score_name}_TOP{topk}_{regime}','final_capital_krw':eq,'return_pct':(eq/START-1)*100,
            'target_100m_hit':eq>=TARGET,'target_hit_date':str(hit_date) if hit_date is not None else '',
            'trades':trades,'max_drawdown_pct':mdd*100},curve,audit


def main():
    data,start,end=load()
    # Use BTC calendar so signal/entry/exit advance exactly one market day each.
    btc=data.get('KRW-BTC')
    if btc is None: raise RuntimeError('KRW-BTC unavailable')
    dates=[x for x in btc.index if start<=x<=end]
    rows=[]; curves={}; all_audit=[]
    for s in ['MOM7','MOM30','ACCEL','FLOW']:
        for k in [1,3,5]:
            for rg in ['BTC50','BTC100']:
                z,cv,au=causal(data,dates,s,k,rg); rows.append(z); curves[z['test']]=cv; all_audit.extend(au)
    res=pd.DataFrame(rows).sort_values('final_capital_krw',ascending=False)
    res.to_csv('backtest_results.csv',index=False)
    audit=pd.DataFrame(all_audit)
    if not audit.empty:
        audit.sort_values('portfolio_return_pct',ascending=False).head(40).to_csv('audit_trades.csv',index=False)
    plt.figure(figsize=(12,6))
    for name in res.head(5).test:
        cv=curves[name]
        if cv: plt.plot([x[0] for x in cv],[x[1] for x in cv],label=name)
    plt.axhline(TARGET,linestyle='--',linewidth=1,label='100M target')
    plt.yscale('log'); plt.ylabel('KRW (log)'); plt.xlabel('Time'); plt.title('Upbit 100X Audit - Lookahead Fixed'); plt.legend(); plt.tight_layout(); plt.savefig('backtest_equity.png',dpi=150)
    print(res.to_string(index=False),flush=True)
    if not audit.empty:
        print('\nTOP AUDITED TRADES',flush=True)
        print(audit.sort_values('portfolio_return_pct',ascending=False).head(20).to_string(index=False),flush=True)
    print('\nAUDIT FIX: signal uses completed day close; entry is NEXT day open; exit is following day open.',flush=True)
    print('AUDIT FILTERS: >=120 prior bars, 20d avg value >=1B KRW, signal-day return <=30%.',flush=True)
    print('NOTE: current-listed-universe survivorship bias is reduced by history requirements but not fully eliminated.',flush=True)

if __name__=='__main__': main()
