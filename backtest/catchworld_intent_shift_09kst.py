"""09:00 KST intent-shift study.
Does not infer human intent. Labels observable continuation/reversal behavior around Upbit daily reset.
"""
from pathlib import Path
import pandas as pd,numpy as np
P=Path('data/incremental/event_09kst_15m.csv');OUT=Path('results/intent_shift_09kst');OUT.mkdir(parents=True,exist_ok=True)
def main():
 x=pd.read_csv(P);pre=x.ret_08_09;post=x.ret_09_10
 x['pre_up']=pre>=.03;x['pre_down']=pre<=-.03
 x['behavior']=np.select([x.pre_up&(post>=.02),x.pre_up&(post<=-.02),x.pre_down&(post<=-.02),x.pre_down&(post>=.02)],['PRE_UP_CONTINUE','PRE_UP_REVERSE','PRE_DOWN_CONTINUE','PRE_DOWN_REVERSE'],default='NEUTRAL')
 x['turn_shift_09']=x.turn_09_10/x.turn_08_09.replace(0,np.nan)
 # Useful observational groups for later V4 microstructure join.
 x['distribution_like_obs']=x.pre_up&(post<0)&(x.turn_shift_09>=1)
 x['continuation_like_obs']=x.pre_up&(post>0)&(x.turn_shift_09>=1)
 x.to_csv(OUT/'intent_shift_events.csv',index=False)
 s=x.groupby('behavior').agg(n=('market','size'),pre_med=('ret_08_09','median'),post_med=('ret_09_10','median'),turn_shift_med=('turn_shift_09','median')).reset_index();s.to_csv(OUT/'summary.csv',index=False);print(s.to_string(index=False))
if __name__=='__main__':main()
