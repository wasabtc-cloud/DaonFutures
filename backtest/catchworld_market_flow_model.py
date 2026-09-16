"""Catch World market-flow regime research layer.

Joins externally collected, timestamp-aligned market features to the Upbit turnover
research dataset. This does NOT claim literal money transfer between asset classes;
it classifies relative risk/flow regimes for backtesting.

Expected market_flow.csv columns (UTC time):
time,nasdaq_ret,sp500_ret,gold_ret,dxy_ret,us10y_change,btc_ret,eth_ret,crypto_turnover_change,btc_dominance_change
"""
import os
import pandas as pd
import numpy as np

SIGNALS=os.getenv('SIGNALS','turnover_research_all.csv')
FLOW=os.getenv('MARKET_FLOW','market_flow.csv')
OUT=os.getenv('OUT','turnover_research_with_market_flow.csv')

s=pd.read_csv(SIGNALS,parse_dates=['time']).sort_values('time')
f=pd.read_csv(FLOW,parse_dates=['time']).sort_values('time')

# Standardize each feature using only trailing history to reduce look-ahead leakage.
features=['nasdaq_ret','sp500_ret','gold_ret','dxy_ret','us10y_change','btc_ret','eth_ret','crypto_turnover_change','btc_dominance_change']
for c in features:
    x=pd.to_numeric(f[c],errors='coerce')
    mu=x.rolling(60,min_periods=20).mean().shift(1)
    sd=x.rolling(60,min_periods=20).std().shift(1).replace(0,np.nan)
    f[c+'_z']=(x-mu)/sd

# Positive = environment relatively favorable to crypto risk assets.
# Weights are intentionally initial research weights, not validated trading constants.
f['crypto_regime_score']=(
    .15*f['nasdaq_ret_z'] + .10*f['sp500_ret_z'] - .10*f['gold_ret_z']
    - .15*f['dxy_ret_z'] - .10*f['us10y_change_z']
    + .20*f['btc_ret_z'] + .15*f['eth_ret_z'] + .15*f['crypto_turnover_change_z']
)
f['crypto_regime']=pd.cut(f.crypto_regime_score,[-np.inf,-.5,.5,np.inf],labels=['RISK_OFF','NEUTRAL','CRYPTO_RISK_ON'])

keep=['time','crypto_regime_score','crypto_regime']+features
m=pd.merge_asof(s,f[keep].sort_values('time'),on='time',direction='backward',tolerance=pd.Timedelta('6h'))
m.to_csv(OUT,index=False)

# Regime report for strategy validation.
def pf(x):
    pos=x[x>0].sum(); neg=-x[x<0].sum(); return pos/neg if neg>0 else np.nan
r=m.groupby('crypto_regime',observed=True).agg(trades=('pnl_tp3_sl2_6h','size'),avg_pnl=('pnl_tp3_sl2_6h','mean'),win_rate=('pnl_tp3_sl2_6h',lambda x:(x>0).mean()))
r['pf']=m.groupby('crypto_regime',observed=True)['pnl_tp3_sl2_6h'].apply(pf)
r.to_csv('market_flow_regime_report.csv')
print(r)
