import os,time,requests,pandas as pd,numpy as np
from datetime import datetime,timezone,timedelta

BASE='https://api.upbit.com/v1'
DAYS=int(os.getenv('DAYS','90')); SHARD=int(os.getenv('SHARD_INDEX','0')); SHARDS=int(os.getenv('SHARD_COUNT','4'))
SURGES=[.05,.10,.20]

def get(path,params=None):
    for n in range(5):
        r=requests.get(BASE+path,params=params,timeout=30)
        if r.status_code==200:return r.json()
        if r.status_code in (418,429):time.sleep(1+n);continue
        r.raise_for_status()
    raise RuntimeError('API retries exhausted')

def markets():
    xs=get('/market/all');return sorted([x['market'] for x in xs if x['market'].startswith('KRW-')])[SHARD::SHARDS]

def candles(m,unit,to=None,count=200):
    p={'market':m,'count':count}
    if to:p['to']=to
    return get(f'/candles/minutes/{unit}',p)

def fetch_hourly(m):
    end=datetime.now(timezone.utc); start=end-timedelta(days=DAYS); rows=[]; to=end
    while to>start:
        x=candles(m,60,to.isoformat().replace('+00:00','Z'),200)
        if not x:break
        rows+=x; oldest=datetime.fromisoformat(x[-1]['candle_date_time_utc']+'+00:00');to=oldest
        if oldest<=start:break
        time.sleep(.12)
    d=pd.DataFrame(rows).drop_duplicates('candle_date_time_utc')
    if d.empty:return d
    d['t']=pd.to_datetime(d.candle_date_time_utc,utc=True);return d.sort_values('t').query('t>=@start')

def anchors(d):
    if len(d)<30:return []
    c=d.trade_price.astype(float).to_numpy(); ts=d.t.tolist(); out=[];last=None
    # first hour where forward move from recent 6h base reaches surge threshold; 6h cooldown
    for i in range(6,len(d)-6):
        base=min(c[i-5:i+1]); future=max(c[i:i+7]); move=future/base-1
        bucket=max([s for s in SURGES if move>=s],default=0)
        if bucket and (last is None or (ts[i]-last)>=pd.Timedelta(hours=6)):
            out.append((ts[i],bucket,move));last=ts[i]
    return out

def fetch5(m,t):
    # 24h before through 6h after anchor
    end=(t+pd.Timedelta(hours=6)).to_pydatetime();start=(t-pd.Timedelta(hours=24)).to_pydatetime();rows=[];to=end
    while to>start:
        x=candles(m,5,to.isoformat().replace('+00:00','Z'),200)
        if not x:break
        rows+=x;old=datetime.fromisoformat(x[-1]['candle_date_time_utc']+'+00:00');to=old
        if old<=start:break
        time.sleep(.12)
    d=pd.DataFrame(rows).drop_duplicates('candle_date_time_utc')
    if d.empty:return d
    d['t']=pd.to_datetime(d.candle_date_time_utc,utc=True);return d.sort_values('t')

def analyze(m,rough,bucket,move,d):
    if len(d)<80:return None
    # exact T0: first 5m candle where 60m rolling high is >=5% above prior 60m rolling low
    px=d.trade_price.astype(float);val=d.candle_acc_trade_price.astype(float)
    prior_low=px.rolling(12,min_periods=6).min().shift(1); fwd_high=px[::-1].rolling(12,min_periods=1).max()[::-1]
    window=(d.t>=rough-pd.Timedelta(hours=3))&(d.t<=rough+pd.Timedelta(hours=6))
    idx=d.index[window & ((fwd_high/prior_low-1)>=.05)]
    if len(idx)==0:return None
    i=idx[0];t0=d.loc[i,'t'];p0=float(px.loc[i]);base=val.rolling(72,min_periods=24).median().shift(1);ratio=val/base
    pre=d[(d.t>=t0-pd.Timedelta(hours=6))&(d.t<t0)].copy();pre['ratio']=ratio.loc[pre.index];pre['ret1h']=px.pct_change(12).loc[pre.index]*100
    # candidate entries: initial inflow, pullback after inflow, additional inflow, breakout
    inflow=pre[(pre.ratio>=1.5)&(pre.ret1h.abs()<3)]
    initial=inflow.index[0] if len(inflow) else None
    additional=inflow[inflow.ratio>=2.0].index[0] if len(inflow[inflow.ratio>=2.0]) else None
    recent=d[(d.t>=t0-pd.Timedelta(hours=2))&(d.t<=t0+pd.Timedelta(hours=1))]
    breakout=recent.index[(px.loc[recent.index]>=px.loc[recent.index].rolling(12,min_periods=6).max().shift(1))]
    breakout=breakout[0] if len(breakout) else i
    pullback=None
    if initial is not None:
        after=d.loc[initial:i]
        z=after.index[(px.loc[after.index].pct_change()<=-.005)]
        if len(z):pullback=z[0]
    rows=[]
    for kind,j in [('initial',initial),('pullback',pullback),('additional',additional),('breakout',breakout)]:
        if j is None:continue
        entry=float(px.loc[j]);future=d[(d.t>d.loc[j,'t'])&(d.t<=d.loc[j,'t']+pd.Timedelta(hours=6))]
        if future.empty:continue
        hi=float(future.high_price.max());lo=float(future.low_price.min())
        rows.append({'shard':SHARD,'market':m,'rough_t':rough,'t0':t0,'bucket':bucket,'event_move_pct':move*100,'entry_type':kind,'entry_t':d.loc[j,'t'],'lead_min':(t0-d.loc[j,'t']).total_seconds()/60,'entry':entry,'mfe_pct':(hi/entry-1)*100,'mae_pct':(lo/entry-1)*100,'hit2':hi>=entry*1.02,'hit3':hi>=entry*1.03,'hit5':hi>=entry*1.05,'value_ratio':float(ratio.loc[j]) if pd.notna(ratio.loc[j]) else np.nan})
    return rows

def main():
    out=[];events=[]
    for k,m in enumerate(markets(),1):
        try:
            h=fetch_hourly(m)
            for rough,bucket,move in anchors(h):
                events.append({'market':m,'rough_t':rough,'bucket':bucket,'move_pct':move*100})
                d=fetch5(m,rough);r=analyze(m,rough,bucket,move,d)
                if r:out+=r
        except Exception as e:print('ERR',m,e,flush=True)
        print(SHARD,k,m,'entries',len(out),flush=True)
    pd.DataFrame(out).to_csv(f'entry_points_shard_{SHARD}.csv',index=False)
    pd.DataFrame(events).to_csv(f'entry_events_shard_{SHARD}.csv',index=False)
    if out:
        x=pd.DataFrame(out);s=x.groupby(['bucket','entry_type']).agg(n=('market','size'),median_lead_min=('lead_min','median'),median_mfe=('mfe_pct','median'),median_mae=('mae_pct','median'),hit2=('hit2','mean'),hit3=('hit3','mean'),hit5=('hit5','mean')).reset_index();s.to_csv(f'entry_summary_shard_{SHARD}.csv',index=False);print(s.to_string(index=False))
if __name__=='__main__':main()
