import pandas as pd
import numpy as np

tr = pd.read_csv('entry_stop_trades.csv')
g = tr[tr['stop_type'].eq('SWING5')].copy()

# Research-only proxy comparison using already-computed OOS path flags.
# It does not place orders and is not portfolio PnL.
def outcome(row, mode):
    stop_r = float(row['net_stop_r'])
    if bool(row['stop_hit']):
        return stop_r
    h2 = bool(row['hit_2r']); h3 = bool(row['hit_3r'])
    if mode == 'FULL_2R':
        return 2.0 if h2 else 0.0
    if mode == 'TP2R_50_RUNNER3R':
        return 2.5 if h3 else (1.0 if h2 else 0.0)
    if mode == 'TP2R_30_RUNNER3R':
        return 2.7 if h3 else (0.6 if h2 else 0.0)
    if mode == 'FULL_3R':
        return 3.0 if h3 else 0.0
    raise ValueError(mode)

modes=['FULL_2R','TP2R_50_RUNNER3R','TP2R_30_RUNNER3R','FULL_3R']
rows=[]; detail=[]
for mode in modes:
    r=g.apply(lambda x: outcome(x,mode),axis=1)
    wins=r[r>0].sum(); losses=-r[r<0].sum()
    pf=wins/losses if losses>0 else np.inf
    rows.append({'strategy':mode,'trades':len(r),'win_rate_pct':(r>0).mean()*100,'avg_r':r.mean(),'median_r':r.median(),'profit_factor_r':pf,'stop_rate_pct':g.stop_hit.mean()*100})
    d=g[['market','label','green_time','entry_time','risk_pct','mfe_pct','mae_pct']].copy(); d['strategy']=mode; d['proxy_r']=r.values; detail.append(d)
summary=pd.DataFrame(rows).sort_values(['profit_factor_r','avg_r'],ascending=False)
summary.to_csv('exit_proxy_grid.csv',index=False)
pd.concat(detail,ignore_index=True).to_csv('exit_proxy_trades.csv',index=False)
print('\nEXIT PROXY OOS SUMMARY\n',summary.to_string(index=False))
print('\nNOTE: proxy only. Next step is minute-by-minute runner/trailing validation before final selection.')
