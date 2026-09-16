"""Causal SELL-decay research features. No future peak is used in signals.
Builds rolling flow/price deterioration features for chronological validation.
"""
import pandas as pd,numpy as np
def add_causal_sell_features(g:pd.DataFrame)->pd.DataFrame:
 g=g.sort_values('time').copy();tr=pd.to_numeric(g.turn_ratio,errors='coerce');px=pd.to_numeric(g.close,errors='coerce')
 g['flow_max_6h']=tr.rolling(6,min_periods=2).max();g['flow_decay_6h']=tr/g.flow_max_6h
 g['flow_max_12h']=tr.rolling(12,min_periods=3).max();g['flow_decay_12h']=tr/g.flow_max_12h
 g['price_max_6h']=px.rolling(6,min_periods=2).max();g['draw_from_6h_high']=px/g.price_max_6h-1
 g['hh_fail']=px<=px.shift(1).rolling(6,min_periods=2).max()
 g['hl_proxy']=px.shift(1).rolling(3,min_periods=2).min();g['hl_break']=px<g.hl_proxy
 # Candidate only; thresholds must be evaluated DEV then frozen before HOLD.
 g['sell_decay_candidate']=(g.flow_decay_6h<=.35)&(g.draw_from_6h_high<=-.03)&g.hh_fail&g.hl_break
 return g
