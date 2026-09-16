"""Forward-only validation for Catch World entry research.

Purpose:
- Do NOT preselect future surge events.
- At each 5m decision point use only candles available up to that point.
- Compare signalled observations with matched non-signal controls.
- Report forward +2/+3/+5% reach, MAE/MFE, simple TP/SL expectancy and PF.

This is intentionally a validation harness: signal thresholds are explicit and must be
re-tested before being promoted to the app's S signal.
"""
import os, time, requests, numpy as np, pandas as pd
from datetime import datetime, timezone, timedelta

BASE='https://api.upbit.com/v1'
DAYS=int(os.getenv('DAYS','90')); SHARD_INDEX=int(os.getenv('SHARD_INDEX','0')); SHARD_COUNT=int(os.getenv('SHARD_COUNT','4'))
FEE=float(os.getenv('ROUNDTRIP_COST','0.0015'))  # fee+slippage stress assumption
HORIZONS=(30,60,180,360)
S=requests.Session(); S.headers.update({'User-Agent':'CatchWorldResearch/1.0'})

def get(path,params=None):
    for k in range(6):
        r=S.get(BASE+path,params=params,timeout=20)
        if r.status_code==429: time.sleep(1.0+k*.5); continue
        r.raise_for_status(); return r.json()
    raise RuntimeError('rate limit')

def markets():
    a=get('/market/all',{'is_details':'false'})
    return sorted(x['market'] for x in a if x['market'].startswith('KRW-'))[SHARD_INDEX::SHARD_COUNT]

def candles(market):
    end=datetime.now(timezone.utc); start=end-timedelta(days=DAYS+3); rows=[]; to=end
    while to>start:
        a=get('/candles/minutes/5',{'market':market,'count':200,'to':to.strftime('%Y-%m-%dT%H:%M:%SZ')})
        if not a: break
        rows.extend(a); oldest=min(pd.to_datetime(x['candle_date_time_utc'],utc=True) for x in a); to=oldest.to_pydatetime()-timedelta(seconds=1)
        if oldest<=start: break
        time.sleep(.11)
    if not rows:return pd.DataFrame()
    d=pd.DataFrame(rows); d['t']=pd.to_datetime(d.candle_date_time_utc,utc=True); d=d.drop_duplicates('t').sort_values('t')
    d=d[d.t>=start]
    for c in ['opening_price','high_price','low_price','trade_price','candle_acc_trade_price','candle_acc_trade_volume']: d[c]=pd.to_numeric(d[c],errors='coerce')
    return d.reset_index(drop=True)

def features(d):
    q=d.candle_acc_trade_price
    # all rolling values are shifted: current decision cannot see future candles.
    base=q.rolling(72,min_periods=36).median().shift(1)
    d['flow']=q/base.replace(0,np.nan)
    d['ret30']=d.trade_price/d.trade_price.shift(6)-1
    d['ret60']=d.trade_price/d.trade_price.shift(12)-1
    d['range']=(d.high_price-d.low_price)/d.opening_price
    # candidate: abnormal turnover while price has not already run too far
    d['sig']=(d.flow>=2.0)&(d.ret30.abs()<=.03)&(d.ret60<=.05)
    # require renewed flow after a quieter bar; still historical/current only
    d['renew']=d.sig&(d.flow.shift(1)<1.7)
    return d

def evaluate(d,market):
    out=[]; n=len(d)
    for i in range(72,n-73):
        is_sig=bool(d.renew.iloc[i])
        # deterministic matched controls: same market/hour, no signal, sampled ~1/12 to limit size
        is_ctl=(not bool(d.sig.iloc[i])) and (i%12==0)
        if not (is_sig or is_ctl): continue
        entry=float(d.trade_price.iloc[i])
        rec={'market':market,'time':d.t.iloc[i].isoformat(),'kind':'signal' if is_sig else 'control','flow':float(d.flow.iloc[i]),'ret30':float(d.ret30.iloc[i])}
        for m in HORIZONS:
            bars=m//5; w=d.iloc[i+1:i+1+bars]
            hi=float(w.high_price.max()/entry-1); lo=float(w.low_price.min()/entry-1); close=float(w.trade_price.iloc[-1]/entry-1)
            rec[f'mfe_{m}']=hi; rec[f'mae_{m}']=lo; rec[f'ret_{m}']=close
            for tp in (.02,.03,.05): rec[f'hit{int(tp*100)}_{m}']=hi>=tp
        # simple 6h TP3/SL2 first-touch; conservative same-bar tie -> stop
        w=d.iloc[i+1:i+73]; pnl=None
        for _,r in w.iterrows():
            hit_sl=r.low_price<=entry*.98; hit_tp=r.high_price>=entry*1.03
            if hit_sl: pnl=-.02-FEE; break
            if hit_tp: pnl=.03-FEE; break
        if pnl is None: pnl=float(w.trade_price.iloc[-1]/entry-1)-FEE
        rec['pnl_tp3_sl2_6h']=pnl; out.append(rec)
    return out

def summary(df):
    rows=[]
    for kind,g in df.groupby('kind'):
        pnl=g.pnl_tp3_sl2_6h; gains=pnl[pnl>0].sum(); losses=-pnl[pnl<0].sum()
        r={'kind':kind,'n':len(g),'win_rate':float((pnl>0).mean()),'expectancy':float(pnl.mean()),'pf':float(gains/losses) if losses else np.nan,'median_flow':float(g.flow.median())}
        for m in HORIZONS:
            r[f'hit2_{m}']=float(g[f'hit2_{m}'].mean());r[f'hit3_{m}']=float(g[f'hit3_{m}'].mean());r[f'hit5_{m}']=float(g[f'hit5_{m}'].mean());r[f'med_mfe_{m}']=float(g[f'mfe_{m}'].median());r[f'med_mae_{m}']=float(g[f'mae_{m}'].median())
        rows.append(r)
    return pd.DataFrame(rows)

def main():
    allrows=[]
    for j,m in enumerate(markets(),1):
        try:
            d=features(candles(m)); allrows+=evaluate(d,m) if len(d)>150 else []
            print(SHARD_INDEX,j,m,'rows',len(allrows),flush=True)
        except Exception as e: print('ERR',m,e,flush=True)
    df=pd.DataFrame(allrows); df.to_csv(f'forward_control_shard_{SHARD_INDEX}.csv',index=False)
    sm=summary(df) if len(df) else pd.DataFrame(); sm.to_csv(f'forward_control_summary_shard_{SHARD_INDEX}.csv',index=False); print(sm.to_string(index=False),flush=True)
if __name__=='__main__': main()
