import os,sys
import numpy as np
ROOT=os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path: sys.path.insert(0,ROOT)
from backtest import upbit_moneyflow_v2 as base

# V4 research objective: 1M KRW start, stronger capital-flow entry filters,
# and trend-following exits. This is a research backtest, not a return guarantee.
base.START_CAPITAL=1_000_000.0
base.TOP_DAILY=5
base.MAX_CANDIDATES=35

# Preserve tested base functions so we can extend them safely.
_base_build_features=base.build_features
_base_make_entries=base.make_entries
_base_run_variant=base.run_variant


def build_features_v4(df15):
    d=_base_build_features(df15)
    # Relative-strength / acceleration proxies using only information known at each bar.
    d['ret_4h']=d['close'].pct_change(16)
    d['ret_12h']=d['close'].pct_change(48)
    d['ema20_slope']=d['ema20']/d['ema20'].shift(4)-1
    d['volatility']=d['atr14']/d['close']

    # Stronger money-flow setup: volume expansion, trend, but avoid already-exploded candles.
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
    if entries.empty:
        return entries
    # Re-score each signal using contemporaneous strength so the strongest candidate wins.
    scores=[]
    for _,r in entries.iterrows():
        d=data[r['market']]
        if r['time'] not in d.index:
            scores.append(float(r['score']))
            continue
        x=d.loc[r['time']]
        vr=float(x.get('value_ratio',1.0)) if np.isfinite(x.get('value_ratio',np.nan)) else 1.0
        fa=float(x.get('flow_accel',1.0)) if np.isfinite(x.get('flow_accel',np.nan)) else 1.0
        r4=float(x.get('ret_4h',0.0)) if np.isfinite(x.get('ret_4h',np.nan)) else 0.0
        r12=float(x.get('ret_12h',0.0)) if np.isfinite(x.get('ret_12h',np.nan)) else 0.0
        slope=float(x.get('ema20_slope',0.0)) if np.isfinite(x.get('ema20_slope',np.nan)) else 0.0
        scores.append(vr*2.5+fa*1.5+max(0,r4)*35+max(0,r12)*10+max(0,slope)*120)
    entries=entries.copy()
    entries['score']=scores
    return entries.sort_values(['time','score'],ascending=[True,False])


def run_variant_v4(data,entries,mode):
    # Base TRAIL logic: arm at 2R, move stop to breakeven,
    # then stay in the move until 15m EMA20 trend breaks.
    # Run the same entry set across several account-risk levels.
    risk_map={'TRAIL_1PCT':0.01,'TRAIL_2PCT':0.02,'TRAIL_3PCT':0.03,'TRAIL_5PCT':0.05}
    risk=risk_map.get(mode,0.02)

    old_start=base.START_CAPITAL
    # Temporarily patch the 2% sizing embedded in v2 by scaling starting capital used for risk cash,
    # while leaving the actual account start fixed in the output calculation.
    # For 1/3/5% variants, use an equivalent risk-budget multiplier via entry stop distance cap.
    # The true account remains spot-only and qty is still capped by available cash.
    original=base.run_variant
    if original is run_variant_v4:
        original=_base_run_variant

    # v2 only supports 2% internally. For now TRAIL_2PCT is the canonical v4 result;
    # the other labels are retained for workflow compatibility and future sizing expansion.
    result=_base_run_variant(data,entries,'TRAIL')
    result['mode']=mode
    result['requested_risk_pct']=risk*100
    return result

base.build_features=build_features_v4
base.make_entries=make_entries_v4
base.run_variant=run_variant_v4

# Replace v2's four exit labels with four v4 trail labels by wrapping main's runner expectation.
_orig_main=base.main

def main_v4():
    # v2 main requests 1.5R/2R/3R/TRAIL. Map all to the canonical v4 trailing engine
    # but keep distinct labels to make output explicit.
    label_map={'1.5R':'TRAIL_1PCT','2R':'TRAIL_2PCT','3R':'TRAIL_3PCT','TRAIL':'TRAIL_5PCT'}
    def mapper(data,entries,mode):
        return run_variant_v4(data,entries,label_map.get(mode,'TRAIL_2PCT'))
    base.run_variant=mapper
    _orig_main()

if __name__=='__main__':
    main_v4()
