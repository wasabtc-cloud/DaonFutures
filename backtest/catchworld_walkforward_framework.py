"""Chronological walk-forward framework for CatchWorld research outputs.
Prevents full-year tune-and-report leakage. Model/scorer is intentionally injected later.
"""
from dataclasses import dataclass
import pandas as pd
@dataclass(frozen=True)
class Fold:
 train_start:pd.Timestamp;train_end:pd.Timestamp;test_start:pd.Timestamp;test_end:pd.Timestamp

def make_folds(times,train_days=180,test_days=30,step_days=30):
 t=pd.to_datetime(pd.Series(times),utc=True).dropna().sort_values(); start=t.min(); end=t.max(); out=[]
 while start+pd.Timedelta(days=train_days+test_days)<=end:
  te=start+pd.Timedelta(days=train_days); xe=te+pd.Timedelta(days=test_days)
  out.append(Fold(start,te,te,xe));start+=pd.Timedelta(days=step_days)
 return out

def split(df,time_col,fold):
 t=pd.to_datetime(df[time_col],utc=True)
 return df[(t>=fold.train_start)&(t<fold.train_end)].copy(),df[(t>=fold.test_start)&(t<fold.test_end)].copy()

def fold_manifest(df,time_col,out_csv):
 fs=make_folds(df[time_col]);pd.DataFrame([f.__dict__ for f in fs]).to_csv(out_csv,index=False);return fs
