#!/usr/bin/env python3
import os, sys
sys.path.insert(0, os.path.dirname(__file__))
import pandas as pd
from backtest_manipulation_ifvg import load_data, resample, add_4h_trend, signal_events

FEE=0.0005
RISK_FRAC=0.01

def run_variant(df, min_stop_pct=0.0025, mode='rr2'):
    x,sigs=signal_events(df,combined=True)
    by_i={}
    for s in sigs: by_i.setdefault(s[0],[]).append(s)
    equity=100.0; peak=equity; maxdd=0.0; trades=[]; i=0
    while i < len(x)-1:
        if i not in by_i: i+=1; continue
        _,side,entry,stop,_=by_i[i][0]
        risk_dist=abs(entry-stop); stop_pct=risk_dist/entry
        if risk_dist<=0 or stop_pct<min_stop_pct or stop_pct>0.05: i+=1; continue
        qty=(equity*RISK_FRAC)/risk_dist
        entry_fee=qty*entry*FEE
        gross=0.0; exit_fee=0.0; outcome='OPEN'; exit_i=None
        if mode=='rr2':
            target=entry + 2*risk_dist if side=='long' else entry-2*risk_dist
            for j in range(i+1,len(x)):
                hi=float(x.loc[j,'high']); lo=float(x.loc[j,'low'])
                hit_sl=(lo<=stop) if side=='long' else (hi>=stop)
                hit_tp=(hi>=target) if side=='long' else (lo<=target)
                if hit_sl and hit_tp: hit_tp=False
                if hit_sl:
                    exit_i=j; px=stop; outcome='SL'; break
                if hit_tp:
                    exit_i=j; px=target; outcome='TP'; break
            if exit_i is None: break
            gross=((px-entry) if side=='long' else (entry-px))*qty
            exit_fee=qty*px*FEE
        else:
            # 50% at fixed +2% move, remaining 50% exits on EMA20 touch or original stop.
            tp1=entry*1.02 if side=='long' else entry*0.98
            half=False
            for j in range(i+1,len(x)):
                hi=float(x.loc[j,'high']); lo=float(x.loc[j,'low']); e20=float(x.loc[j,'ema20'])
                hit_sl=(lo<=stop) if side=='long' else (hi>=stop)
                hit_tp1=(hi>=tp1) if side=='long' else (lo<=tp1)
                if not half:
                    if hit_sl and hit_tp1: hit_tp1=False
                    if hit_sl:
                        exit_i=j; px=stop; gross=((px-entry) if side=='long' else (entry-px))*qty; exit_fee=qty*px*FEE; outcome='SL'; break
                    if hit_tp1:
                        half=True; qh=qty*0.5
                        gross+=((tp1-entry) if side=='long' else (entry-tp1))*qh
                        exit_fee+=qh*tp1*FEE
                else:
                    trend_exit=(lo<=e20) if side=='long' else (hi>=e20)
                    if hit_sl or trend_exit:
                        exit_i=j; px=stop if hit_sl else e20; qh=qty*0.5
                        gross+=((px-entry) if side=='long' else (entry-px))*qh
                        exit_fee+=qh*px*FEE
                        outcome='TP1+SL' if hit_sl else 'TP1+EMA20'; break
            if exit_i is None: break
        pnl=gross-entry_fee-exit_fee
        eq0=equity; equity+=pnl; peak=max(peak,equity); maxdd=max(maxdd,(peak-equity)/peak)
        trades.append({'entry_time':x.loc[i,'time'],'exit_time':x.loc[exit_i,'time'],'side':side,'entry':entry,'stop':stop,'stop_pct':stop_pct,'mode':mode,'outcome':outcome,'pnl':pnl,'equity_before':eq0,'equity_after':equity})
        i=exit_i+1
    t=pd.DataFrame(trades)
    if t.empty: return t, {'trades':0,'win_rate':0,'final_equity':equity,'return_pct':0,'max_dd_pct':0,'profit_factor':0}
    wins=t.pnl[t.pnl>0].sum(); losses=-t.pnl[t.pnl<0].sum()
    return t, {'trades':len(t),'win_rate':(t.pnl>0).mean()*100,'final_equity':equity,'return_pct':(equity/100-1)*100,'max_dd_pct':maxdd*100,'profit_factor':wins/losses if losses>0 else 999,'avg_pnl':t.pnl.mean(),'longs':int((t.side=='long').sum()),'shorts':int((t.side=='short').sum())}

def main():
    os.makedirs('backtest_opt_results',exist_ok=True)
    base=load_data('2023-09','2026-08')
    d=add_4h_trend(resample(base,'15min'),base)
    rows=[]
    for minsp in [0.0025,0.0030,0.0040,0.0050]:
        for mode in ['rr2','half2pct_ema20']:
            tr,st=run_variant(d,minsp,mode)
            st.update({'timeframe':'15m','min_stop_pct':minsp*100,'exit_mode':mode,'fee_side_pct':FEE*100,'risk_per_trade_pct':RISK_FRAC*100})
            rows.append(st); tr.to_csv(f'backtest_opt_results/trades_{int(minsp*10000)}bp_{mode}.csv',index=False)
            print('OPT_RESULT',st,flush=True)
    out=pd.DataFrame(rows).sort_values(['return_pct','profit_factor'],ascending=False)
    out.to_csv('backtest_opt_results/summary.csv',index=False)
    print('\n=== OPTIMIZATION SUMMARY ===')
    print(out.to_string(index=False))

if __name__=='__main__': main()
