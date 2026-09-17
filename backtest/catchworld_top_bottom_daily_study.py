"""Daily cross-sectional contrast: TOP/BOTTOM/NEUTRAL without treating 09 KST display rank as causal.
Uses rolling/event features; designed to reduce winner-only selection bias.
"""
from pathlib import Path
import pandas as pd,numpy as np
P=Path('data/incremental/event_09kst_15m.csv');OUT=Path('results/top_bottom_daily');OUT.mkdir(parents=True,exist_ok=True)
def main():
 x=pd.read_csv(P);x['post_6h']=(1+x[['ret_09_10','ret_10_12','ret_12_15']].fillna(0)).prod(axis=1)-1
 x['rank_pct']=x.groupby('day').post_6h.rank(pct=True,method='average')
 x['group']=np.select([x.rank_pct>=.9,x.rank_pct<=.1],['TOP','BOTTOM'],default='NEUTRAL')
 x['pre_08_09']=x.ret_08_09;x['turn_shift']=x.turn_09_10/x.turn_08_09.replace(0,np.nan)
 x.to_csv(OUT/'daily_contrast.csv',index=False)
 s=x.groupby('group').agg(n=('market','size'),pre_med=('pre_08_09','median'),post6_med=('post_6h','median'),turn_shift_med=('turn_shift','median')).reset_index();s.to_csv(OUT/'summary.csv',index=False);print(s.to_string(index=False))
if __name__=='__main__':main()
