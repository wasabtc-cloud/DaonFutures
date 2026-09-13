import os, sys, math
from datetime import datetime, timedelta, timezone
import numpy as np
import pandas as pd

ROOT=os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path: sys.path.insert(0,ROOT)
from backtest import upbit_moneyflow_v2 as v2

START=1_000_000.0
RISKS=(0.02,0.03,0.05)


def run_3r(data, entries, risk_frac):
    grouped={t:g for t,g in entries.groupby('time')}
    timeline=sorted(set().union(*[set(d.index) for d in data.values()]))
    capital=START; peak=START; mdd=0.0; pos=None; trades=[]; last_day=None
    for t in timeline:
        if pos is not None and t in data[pos['market']].index:
            bar=data[pos['market']].loc[t]; exit_price=None; reason=None
            if bar['low']<=pos['stop']:
                exit_price=pos['stop']*(1-v2.SLIPPAGE); reason='stop'
            elif bar['high']>=pos['entry']+3*pos['risk']:
                exit_price=(pos['entry']+3*pos['risk'])*(1-v2.SLIPPAGE); reason='3R'
            if exit_price is not None:
                capital += pos['qty']*exit_price*(1-v2.FEE)
                ret=capital/pos['before']-1
                trades.append(ret*100); pos=None
        day=t.floor('D')
        if pos is None and t in grouped and day!=last_day:
            for _,sig in grouped[t].iterrows():
                m=sig['market']
                if m not in data or t not in data[m].index: continue
                entry=float(data[m].loc[t,'open'])*(1+v2.SLIPPAGE); stop=float(sig['stop']); r=entry-stop
                if r<=0: continue
                qty=min(capital*risk_frac/r,(capital*(1-v2.FEE))/entry)
                if qty<=0: continue
                used=qty*entry/(1-v2.FEE); reserve=max(0.0,capital-used); before=capital
                pos={'market':m,'entry':entry,'stop':stop,'risk':r,'qty':qty,'before':before}
                capital=reserve; last_day=day; break
        eq=capital
        if pos is not None and t in data[pos['market']].index:
            eq += pos['qty']*float(data[pos['market']].loc[t,'close'])*(1-v2.FEE)
        peak=max(peak,eq); mdd=max(mdd,(peak-eq)/peak if peak else 0)
    if pos is not None:
        m=pos['market']; px=float(data[m].iloc[-1]['close'])*(1-v2.SLIPPAGE)
        capital += pos['qty']*px*(1-v2.FEE); trades.append((capital/pos['before']-1)*100)
    tr=np.array(trades,dtype=float)
    wins=tr[tr>0]; losses=tr[tr<=0]
    pf=wins.sum()/(-losses.sum()) if len(losses) and -losses.sum()>0 else math.inf
    wr=(tr>0).mean()*100 if len(tr) else 0.0
    return {'risk_pct':risk_frac*100,'final_capital_krw':capital,'return_pct':(capital/START-1)*100,
            'trades':len(tr),'win_rate_pct':wr,'profit_factor':pf,'max_drawdown_pct':mdd*100}


def main():
    end=datetime.now(timezone.utc).replace(second=0,microsecond=0); start=end-timedelta(days=v2.DAYS); warm=start-timedelta(days=40)
    markets=v2.get_json('/market/all',{'is_details':'false'}); krw=sorted(x['market'] for x in markets if x['market'].startswith('KRW-'))
    daily={}; freq={}
    for i,m in enumerate(krw,1):
        try:
            dd=v2.fetch_days(m,start-timedelta(days=8),end)
            if len(dd)>=10: daily[m]=dd
        except Exception as e: print('daily skip',m,e)
        if i%20==0: print('daily',i,'/',len(krw))
    all_dates=sorted(set().union(*[set(x.index.floor('D')) for x in daily.values()])) if daily else []
    universe={}
    for day in all_dates:
        if day<pd.Timestamp(start).floor('D'): continue
        prev=day-pd.Timedelta(days=1); vals=[]
        for m,dd in daily.items():
            hit=dd[dd.index.floor('D')==prev]
            if len(hit): vals.append((m,float(hit.iloc[-1]['value'])))
        vals.sort(key=lambda x:x[1],reverse=True); picks=[m for m,_ in vals[:v2.TOP_DAILY]]; universe[day]=set(picks)
        for m in picks: freq[m]=freq.get(m,0)+1
    candidates=[m for m,_ in sorted(freq.items(),key=lambda kv:kv[1],reverse=True)[:v2.MAX_CANDIDATES]]
    if 'KRW-BTC' not in candidates: candidates.append('KRW-BTC')
    data={}
    for i,m in enumerate(candidates,1):
        try:
            df=v2.fetch_candles(m,15,warm,end)
            if len(df)>1000: data[m]=v2.build_features(df); print('15m',i,'/',len(candidates),m,len(df))
        except Exception as e: print('15m skip',m,e)
    btc=v2.build_btc_filter(data['KRW-BTC'][['open','high','low','close','volume','value']])
    entries=v2.make_entries(data,universe,btc)
    if entries.empty: raise RuntimeError('No entries generated')
    rows=[run_3r(data,entries,r) for r in RISKS]
    out=pd.DataFrame(rows).sort_values('final_capital_krw',ascending=False)
    out.insert(0,'strategy','Upbit MoneyFlow v3 3R risk sweep')
    out.to_csv('upbit_moneyflow_v3_results.csv',index=False)
    print(out.to_string(index=False))

if __name__=='__main__': main()
