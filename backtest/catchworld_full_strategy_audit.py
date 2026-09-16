"""CatchWorld full strategy audit: test early big-winner filters without look-ahead."""
from pathlib import Path
import pandas as pd, numpy as np
DATA=Path('data/flow_path'); OUT=Path('results/full_strategy_audit'); OUT.mkdir(parents=True,exist_ok=True)
FEE=.0005

def factor(ret): return (1+ret)*(1-FEE)/(1+FEE)

def main():
 d=pd.concat((pd.read_csv(f) for f in sorted(DATA.glob('*.csv'))),ignore_index=True)
 d['entry_time']=pd.to_datetime(d.entry_time,utc=True,errors='coerce'); d=d.dropna(subset=['market','entry_time','offset_min','price'])
 e=d[d.offset_min.eq(0)].copy(); e['kst_hour']=(e.entry_time+pd.Timedelta(hours=9)).dt.hour
 e=e[(e.flow>=10)&e.ret30.between(-.025,-.020)&e.kst_hour.between(6,8)].copy()
 keys=set(zip(e.market,e.entry_time.astype(str))); d['_key']=list(zip(d.market,d.entry_time.astype(str))); d=d[d._key.isin(keys)]
 rows=[]
 for (m,t),p in d.groupby(['market','entry_time'],sort=False):
  p=p.sort_values('offset_min'); z=p[p.offset_min.eq(0)]
  if z.empty: continue
  ep=float(z.iloc[0].price); flow=float(z.iloc[0].flow)
  fut=p[(p.offset_min>0)&(p.offset_min<=360)]
  if fut.empty: continue
  o={'market':m,'entry_time':t,'flow':flow,'entry':ep}
  for h in [30,60]:
   q=fut[fut.offset_min<=h]; rr=q.price/ep-1; o[f'mfe{h}']=rr.max(); o[f'mae{h}']=rr.min();
   at=fut[fut.offset_min.eq(h)]; o[f'ret{h}']=np.nan if at.empty else float(at.iloc[0].price/ep-1)
  # causal entries at checkpoint: use checkpoint close, then only future bars
  for h in [30,60]:
   at=fut[fut.offset_min.eq(h)]
   if at.empty: continue
   cp=float(at.iloc[0].price); after=fut[fut.offset_min>h]
   # exit variants from checkpoint: 6h end, TP10/SL2, TP10/SL3; close-only ordering
   end=float(after.iloc[-1].price) if len(after) else cp; o[f'endret_h{h}']=end/cp-1
   for sl in [.02,.03]:
    ex=end; reason='TIME'
    for _,r in after.iterrows():
     x=float(r.price/cp-1)
     if x<=-sl: ex=cp*(1-sl); reason='SL'; break
     if x>=.10: ex=cp*1.10; reason='TP'; break
    o[f'net_h{h}_sl{int(sl*100)}']=factor(ex/cp-1)-1; o[f'reason_h{h}_sl{int(sl*100)}']=reason
  rows.append(o)
 ev=pd.DataFrame(rows).sort_values('entry_time'); ev.to_csv(OUT/'events.csv',index=False)
 # candidate filters are based only on data known at checkpoint. No future MFE after checkpoint used as filter.
 rules={
  'ALL_30':pd.Series(True,index=ev.index),
  '30_STRONG':(ev.mfe30>=.02)&(ev.mae30>=-.01)&(ev.ret30>=0),
  '30_MODERATE':(ev.mfe30>=.015)&(ev.mae30>=-.012)&(ev.ret30>=0),
  'ALL_60':pd.Series(True,index=ev.index),
  '60_STRONG':(ev.mfe60>=.04)&(ev.mae60>=-.015)&(ev.ret60>=.02),
  '60_MODERATE':(ev.mfe60>=.03)&(ev.mae60>=-.02)&(ev.ret60>=.01),
 }
 out=[]
 for name,mask in rules.items():
  h=30 if '30' in name else 60
  q=ev[mask & ev[f'net_h{h}_sl2'].notna()].copy()
  for sl in [2,3]:
   col=f'net_h{h}_sl{sl}'; vals=q[col].dropna(); eq=(1+vals).cumprod(); peak=eq.cummax(); mdd=((eq/peak)-1).min() if len(eq) else np.nan
   gains=vals[vals>0].sum(); losses=-vals[vals<0].sum(); pf=gains/losses if losses>0 else np.nan
   out.append({'rule':name,'checkpoint_min':h,'sl_pct':sl,'trades':len(vals),'win_pct':100*(vals>0).mean() if len(vals) else np.nan,'avg_net_pct':100*vals.mean() if len(vals) else np.nan,'pf':pf,'equity_multiple':eq.iloc[-1] if len(eq) else np.nan,'mdd_pct':100*mdd if len(eq) else np.nan,'tp10_pct':100*(q[f'reason_h{h}_sl{sl}']=='TP').mean() if len(q) else np.nan})
 res=pd.DataFrame(out); res.to_csv(OUT/'audit_summary.csv',index=False)
 print('EVENTS',len(ev)); print(res.to_string(index=False));
 print('AUDIT: checkpoint filters use only <= checkpoint data; exits use only > checkpoint data. Caveat: 5m close path cannot resolve intrabar high/low or exact fill/slippage.',flush=True)
if __name__=='__main__': main()
