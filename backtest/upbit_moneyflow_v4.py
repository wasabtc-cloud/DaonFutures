import math, os, sys
import numpy as np
import pandas as pd
ROOT=os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path: sys.path.insert(0,ROOT)
from backtest import upbit_moneyflow_v2 as base

base.START_CAPITAL=1_000_000.0
base.TOP_DAILY=5
base.MAX_CANDIDATES=35
_base_build_features=base.build_features
_base_make_entries=base.make_entries


def build_features_v4(df15):
    d=_base_build_features(df15)
    d['ret_4h']=d['close'].pct_change(16)
    d['ret_12h']=d['close'].pct_change(48)
    d['ema20_slope']=d['ema20']/d['ema20'].shift(4)-1
    d['volatility']=d['atr14']/d['close']
    d['breakout']=(
        (d['close']>d['prior20_high']) &
        (d['value_ratio']>=2.25) &
        (d['flow_accel']>=1.12) &
        (d['mom_1h']>0.003) & (d['mom_1h']<0.045) &
        (d['ret_4h']>0.005) & (d['ret_4h']<0.12) &
        (d['ret_12h']>0) &
        (d['ema20_slope']>0) &
        (d['bar_ret']>0) & (d['bar_ret']<0.025) &
        (d['volatility']>0.004) & (d['volatility']<0.08)
    )
    return d


def make_entries_v4(data,daily_universe,btc_filter):
    entries=_base_make_entries(data,daily_universe,btc_filter)
    if entries.empty: return entries
    scores=[]
    for _,r in entries.iterrows():
        d=data[r['market']]
        if r['time'] not in d.index:
            scores.append(float(r['score'])); continue
        x=d.loc[r['time']]
        def f(k,default=0.0):
            v=x.get(k,np.nan)
            return float(v) if np.isfinite(v) else default
        scores.append(f('value_ratio',1)*2.5+f('flow_accel',1)*1.5+max(0,f('ret_4h'))*35+max(0,f('ret_12h'))*10+max(0,f('ema20_slope'))*120)
    entries=entries.copy(); entries['score']=scores
    return entries.sort_values(['time','score'],ascending=[True,False])


def run_variant(data, entries, mode):
    grouped={t:g for t,g in entries.groupby('time')}
    timeline=sorted(set().union(*[set(d.index) for d in data.values()]))
    capital=base.START_CAPITAL; peak=capital; max_dd=0.0
    position=None; trades=[]; eq_rows=[]; last_entry_day=None

    for t in timeline:
        if position is not None:
            m=position['market']; d=data[m]
            if t in d.index:
                bar=d.loc[t]; exit_price=None; reason=None
                r=position['risk']; entry=position['entry']
                if bar['low']<=position['stop']:
                    exit_price=position['stop']*(1-base.SLIPPAGE); reason='stop'
                else:
                    two_r=entry+2*r; three_r=entry+3*r
                    if mode=='A_3R_FIXED':
                        if bar['high']>=three_r:
                            exit_price=three_r*(1-base.SLIPPAGE); reason='3R'
                    else:
                        if (not position['partial_done']) and bar['high']>=two_r:
                            frac={'B_50_EMA20':0.50,'C_30_ATR':0.30,'D_20_EMA1H':0.20}[mode]
                            sell_qty=position['qty']*frac
                            proceeds=sell_qty*two_r*(1-base.SLIPPAGE)*(1-base.FEE)
                            capital+=proceeds
                            position['qty']-=sell_qty
                            position['partial_done']=True
                            position['stop']=max(position['stop'],entry)
                            position['highest']=max(position['highest'],float(bar['high']))
                        if position['partial_done']:
                            position['highest']=max(position['highest'],float(bar['high']))
                            if mode=='B_50_EMA20' and bar['close']<bar['ema20']:
                                exit_price=float(bar['close'])*(1-base.SLIPPAGE); reason='ema20'
                            elif mode=='C_30_ATR':
                                trail=position['highest']-3.0*float(bar['atr14'])
                                position['stop']=max(position['stop'],trail)
                            elif mode=='D_20_EMA1H':
                                # Approximate 1h EMA20 using 15m EMA80 for completed-bar trend following.
                                ema80=d['close'].ewm(span=80,adjust=False).mean().loc[t]
                                if bar['close']<ema80:
                                    exit_price=float(bar['close'])*(1-base.SLIPPAGE); reason='ema1h_proxy'

                if exit_price is not None:
                    capital+=position['qty']*exit_price*(1-base.FEE)
                    ret=capital/position['capital_before']-1
                    trades.append({'market':m,'entry_time':position['time'],'exit_time':t,'return_pct':ret*100,'reason':reason})
                    position=None

        day=t.floor('D')
        if position is None and t in grouped and day!=last_entry_day:
            for _,sig in grouped[t].iterrows():
                m=sig['market']
                if m not in data or t not in data[m].index: continue
                entry=float(data[m].loc[t,'open'])*(1+base.SLIPPAGE)
                stop=float(sig['stop']); risk=entry-stop
                if risk<=0: continue
                risk_cash=capital*0.02
                qty=min(risk_cash/risk,(capital*(1-base.FEE))/entry)
                if qty<=0: continue
                cash_used=qty*entry/(1-base.FEE)
                reserve=max(0.0,capital-cash_used)
                before=capital
                position={'market':m,'time':t,'entry':entry,'stop':stop,'risk':risk,'qty':qty,'capital_before':before,
                          'partial_done':False,'highest':entry}
                capital=reserve; last_entry_day=day; break

        eq=capital
        if position is not None:
            m=position['market']
            if t in data[m].index: eq+=position['qty']*float(data[m].loc[t,'close'])*(1-base.FEE)
        peak=max(peak,eq); max_dd=max(max_dd,(peak-eq)/peak if peak else 0)
        eq_rows.append((t,eq))

    if position is not None:
        m=position['market']; last=data[m].iloc[-1]
        capital+=position['qty']*float(last['close'])*(1-base.SLIPPAGE)*(1-base.FEE)
        ret=capital/position['capital_before']-1
        trades.append({'market':m,'entry_time':position['time'],'exit_time':data[m].index[-1],'return_pct':ret*100,'reason':'end'})

    tr=pd.DataFrame(trades)
    if len(tr):
        wins=tr[tr.return_pct>0]; losses=tr[tr.return_pct<=0]
        gw=wins.return_pct.sum(); gl=-losses.return_pct.sum(); pf=gw/gl if gl>0 else math.inf; wr=len(wins)/len(tr)*100
    else: pf=0.0; wr=0.0
    return {'mode':mode,'final':capital,'return_pct':(capital/base.START_CAPITAL-1)*100,'trades':len(tr),'win_rate_pct':wr,
            'profit_factor':pf,'mdd_pct':max_dd*100,'trades_df':tr,'equity':pd.DataFrame(eq_rows,columns=['time','equity'])}


base.build_features=build_features_v4
base.make_entries=make_entries_v4


def main_v4():
    from datetime import datetime,timedelta,timezone
    import matplotlib.pyplot as plt
    end=datetime.now(timezone.utc).replace(second=0,microsecond=0)
    start=end-timedelta(days=base.DAYS); warmup=start-timedelta(days=40)
    markets=base.get_json('/market/all',{'is_details':'false'})
    krw=sorted([x['market'] for x in markets if x['market'].startswith('KRW-')])
    daily={}; freq={}
    for m in krw:
        try:
            dd=base.fetch_days(m,start-timedelta(days=8),end)
            if len(dd)>=10: daily[m]=dd
        except Exception: pass
    all_dates=sorted(set().union(*[set(x.index.floor('D')) for x in daily.values()])) if daily else []
    daily_universe={}
    for day in all_dates:
        if day<pd.Timestamp(start).floor('D'): continue
        prev=day-pd.Timedelta(days=1); vals=[]
        for m,dd in daily.items():
            hit=dd[dd.index.floor('D')==prev]
            if len(hit): vals.append((m,float(hit.iloc[-1]['value'])))
        vals.sort(key=lambda x:x[1],reverse=True); picks=[m for m,_ in vals[:base.TOP_DAILY]]
        daily_universe[day]=set(picks)
        for m in picks: freq[m]=freq.get(m,0)+1
    candidates=[m for m,_ in sorted(freq.items(),key=lambda kv:kv[1],reverse=True)[:base.MAX_CANDIDATES]]
    if 'KRW-BTC' not in candidates: candidates.append('KRW-BTC')
    data={}
    for m in candidates:
        try:
            df=base.fetch_candles(m,15,warmup,end)
            if len(df)>1000: data[m]=build_features_v4(df)
        except Exception as e: print('skip',m,e)
    btc_filter=base.build_btc_filter(data['KRW-BTC'][['open','high','low','close','volume','value']])
    entries=make_entries_v4(data,daily_universe,btc_filter)
    print('V4 entries:',len(entries))
    if entries.empty: raise RuntimeError('No entries generated')

    modes=['A_3R_FIXED','B_50_EMA20','C_30_ATR','D_20_EMA1H']
    variants=[run_variant(data,entries,m) for m in modes]
    rows=[]
    for v in variants:
        rows.append({'strategy':'Upbit MoneyFlow V4','exit_mode':v['mode'],'start_capital_krw':base.START_CAPITAL,
                     'final_capital_krw':round(v['final'],2),'return_pct':round(v['return_pct'],4),'trades':v['trades'],
                     'win_rate_pct':round(v['win_rate_pct'],4),'profit_factor':round(v['profit_factor'],4) if np.isfinite(v['profit_factor']) else 'inf',
                     'max_drawdown_pct':round(v['mdd_pct'],4),'risk_per_trade_pct':2.0})
    res=pd.DataFrame(rows).sort_values('final_capital_krw',ascending=False)
    res.to_csv('backtest_results.csv',index=False)
    for v in variants: v['trades_df'].to_csv(f"v4_{v['mode']}_trades.csv",index=False)
    plt.figure(figsize=(12,6))
    for v in variants:
        ec=v['equity'].drop_duplicates('time').set_index('time'); plt.plot(ec.index,ec.equity,label=v['mode'])
    plt.legend(); plt.title('Upbit MoneyFlow V4 - 4 exit variants'); plt.ylabel('KRW'); plt.xlabel('Time'); plt.tight_layout(); plt.savefig('backtest_equity.png',dpi=150)
    print(res.to_string(index=False))

if __name__=='__main__': main_v4()
