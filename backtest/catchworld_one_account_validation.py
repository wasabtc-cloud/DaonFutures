"""One-account chronological validation on 1y Flow Path. No overlapping positions, no future-data entry filter."""
from pathlib import Path
import pandas as pd, numpy as np
DATA=Path('data/flow_path'); OUT=Path('results/one_account'); OUT.mkdir(parents=True,exist_ok=True)
FEE=.0005; START=1_000_000.0

def net_factor(r): return (1+r)*(1-FEE)/(1+FEE)

def main():
 d=pd.concat((pd.read_csv(f) for f in sorted(DATA.glob('*.csv'))),ignore_index=True)
 d['entry_time']=pd.to_datetime(d.entry_time,utc=True,errors='coerce'); d=d.dropna(subset=['market','entry_time','offset_min','price'])
 e=d[d.offset_min.eq(0)].copy(); e['kst_hour']=(e.entry_time+pd.Timedelta(hours=9)).dt.hour
 e=e[(e.flow>=10)&e.ret30.between(-.025,-.020)&e.kst_hour.between(6,8)].sort_values(['entry_time','flow'],ascending=[True,False])
 keys=set(zip(e.market,e.entry_time.astype(str))); d['_key']=list(zip(d.market,d.entry_time.astype(str))); d=d[d._key.isin(keys)]
 paths={}
 for (m,t),p in d.groupby(['market','entry_time'],sort=False): paths[(m,t)]=p.sort_values('offset_min')
 configs=[]
 for tp in [.03,.05,.08,.10]:
  for sl in [.015,.02,.025,.03]: configs.append((tp,sl))
 summaries=[]; ledgers=[]
 for tp,sl in configs:
  equity=START; free_at=pd.Timestamp.min.tz_localize('UTC'); trades=[]
  for _,r in e.iterrows():
   t=r.entry_time
   if t<free_at: continue
   p=paths.get((r.market,t));
   if p is None: continue
   z=p[p.offset_min.eq(0)]; fut=p[(p.offset_min>0)&(p.offset_min<=360)]
   if z.empty or fut.empty: continue
   ep=float(z.iloc[0].price); ex=float(fut.iloc[-1].price); reason='TIME'; exit_min=float(fut.iloc[-1].offset_min)
   # close-only path: conservative when threshold is observed on a 5m close; cannot model intrabar ordering.
   for _,b in fut.iterrows():
    rr=float(b.price/ep-1)
    if rr<=-sl: ex=ep*(1-sl); reason='SL'; exit_min=float(b.offset_min); break
    if rr>=tp: ex=ep*(1+tp); reason='TP'; exit_min=float(b.offset_min); break
   nr=net_factor(ex/ep-1)-1; before=equity; equity*=1+nr; free_at=t+pd.Timedelta(minutes=exit_min)
   trades.append({'config':f'TP{tp*100:.1f}_SL{sl*100:.1f}','market':r.market,'entry_time':t,'exit_time':free_at,'flow':r.flow,'ret30':r.ret30,'reason':reason,'net_ret':nr,'equity_before':before,'equity_after':equity})
  q=pd.DataFrame(trades)
  if q.empty: continue
  eq=q.equity_after; peak=pd.concat([pd.Series([START]),eq],ignore_index=True).cummax().iloc[1:].set_axis(q.index); dd=eq/peak-1
  v=q.net_ret; gains=v[v>0].sum(); losses=-v[v<0].sum(); pf=gains/losses if losses>0 else np.nan
  summaries.append({'tp_pct':tp*100,'sl_pct':sl*100,'trades':len(q),'final_krw':equity,'multiple':equity/START,'win_pct':100*(v>0).mean(),'avg_net_pct':100*v.mean(),'pf':pf,'mdd_pct':100*dd.min(),'tp_pct_trades':100*(q.reason=='TP').mean(),'sl_pct_trades':100*(q.reason=='SL').mean(),'time_pct_trades':100*(q.reason=='TIME').mean()})
  ledgers.append(q)
 res=pd.DataFrame(summaries).sort_values('multiple',ascending=False); res.to_csv(OUT/'summary.csv',index=False)
 pd.concat(ledgers,ignore_index=True).to_csv(OUT/'ledger_all.csv',index=False)
 print('RAW_SIGNALS',len(e)); print(res.to_string(index=False));
 print('AUDIT: one position at a time; chronological; current fee 0.05% each side; no slippage; 5m close-only threshold detection. Results are research estimates, not executable tick-level fills.',flush=True)
if __name__=='__main__': main()
