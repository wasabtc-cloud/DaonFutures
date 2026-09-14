import runpy, pandas as pd
# Reuse the existing minute validator after generating both stop candidates.
# This comparison script is intentionally separate so prior validation stays reproducible.
runpy.run_path('backtest/youtube_10_strategies.py', run_name='__main__')
tr=pd.read_csv('entry_stop_trades.csv')
print('\nSWING10 VS SWING20 INPUT GRID\n')
print(tr[tr.stop_type.isin(['SWING10','SWING20'])].groupby('stop_type').agg(trades=('market','size'),avg_risk_pct=('risk_pct','mean'),stop_hit_pct=('stop_hit','mean'),hit_2r_pct=('hit_2r','mean'),hit_3r_pct=('hit_3r','mean')).to_string())
print('\nNext: exact minute-path comparison uses the same 2R 50% + 20-bar trailing exit for both stop candidates.')
