"""Enrich realized 9AM top-5 movers with CoinGecko metadata and event-date market cap.

Best-effort research enrichment. Coin/project country is not standardized in crypto, so
country_of_origin may be blank/Unknown. CoinGecko symbol matching is recorded with a
quality flag and ambiguous symbols are resolved to the highest-current-market-cap coin.
"""
from __future__ import annotations

import json
import time
from pathlib import Path

import numpy as np
import pandas as pd
import requests

OUT=Path('results_9am')
CACHE=Path('.cache/9am-metadata')
CACHE.mkdir(parents=True,exist_ok=True)
CG='https://api.coingecko.com/api/v3'
UA={'User-Agent':'DaonFutures-9AM-Research/1.0'}


def cg_get(path,params=None,retries=8,sleep_after=1.25):
    key=(path+'?'+json.dumps(params or {},sort_keys=True,ensure_ascii=False)).replace('/','_').replace('?','_').replace(':','_')
    fp=CACHE/(str(abs(hash(key)))+'.json')
    if fp.exists():
        try:return json.loads(fp.read_text())
        except Exception:pass
    for k in range(retries):
        r=requests.get(CG+path,params=params,headers=UA,timeout=30)
        if r.status_code==429:
            time.sleep(min(60,3*(k+1))); continue
        try:r.raise_for_status()
        except Exception:
            if k==retries-1:return None
            time.sleep(2*(k+1)); continue
        data=r.json(); fp.write_text(json.dumps(data,ensure_ascii=False)); time.sleep(sleep_after); return data
    return None


def market_index():
    rows=[]
    for page in range(1,6):
        js=cg_get('/coins/markets',{'vs_currency':'krw','order':'market_cap_desc','per_page':250,'page':page,'sparkline':'false'},sleep_after=.7)
        if not js:break
        rows.extend(js)
        if len(js)<250:break
    idx={}
    for x in rows:
        sym=str(x.get('symbol','')).upper()
        idx.setdefault(sym,[]).append(x)
    return idx


def simplify_sector(categories):
    s=' | '.join(categories or []).lower()
    checks=[
        ('Meme',['meme']),('AI',['artificial intelligence','ai ']),
        ('Gaming/Metaverse',['gaming','gamefi','metaverse']),
        ('DeFi',['defi','decentralized finance','yield']),
        ('RWA',['real world assets','rwa']),
        ('L2',['layer 2','rollup']),
        ('L1',['layer 1','smart contract platform']),
        ('Storage/Infrastructure',['storage','depin','infrastructure','oracle','interoperability']),
        ('Payments',['payment','payments','remittance'])]
    for label,keys in checks:
        if any(k in s for k in keys):return label
    return 'Other'


def cap_bucket(x):
    if pd.isna(x) or x<=0:return 'Unknown'
    # KRW buckets: <100억, 100~500억, 500~1,000억, 1,000~5,000억, >=5,000억
    if x<10_000_000_000:return '<100억'
    if x<50_000_000_000:return '100~500억'
    if x<100_000_000_000:return '500~1,000억'
    if x<500_000_000_000:return '1,000~5,000억'
    return '5,000억 이상'


def historical_cap(coin_id,day):
    js=cg_get(f'/coins/{coin_id}/history',{'date':pd.Timestamp(day).strftime('%d-%m-%Y'),'localization':'false'})
    try:return float(js['market_data']['market_cap']['krw'])
    except Exception:return np.nan


def main():
    src=OUT/'upbit_9am_realized_top5_daily.csv'
    if not src.exists():raise FileNotFoundError(src)
    df=pd.read_csv(src)
    idx=market_index()
    meta={}
    for market in sorted(df.market.unique()):
        sym=market.split('-',1)[1].upper(); cands=idx.get(sym,[])
        if not cands:
            meta[market]={'coin_id':None,'match_quality':'unmatched','country':'Unknown','sector':'Unknown','categories':'','current_market_cap_krw':np.nan}
            continue
        cands=sorted(cands,key=lambda x:(x.get('market_cap') or 0),reverse=True)
        chosen=cands[0]; quality='exact_symbol_unique' if len(cands)==1 else 'symbol_ambiguous_highest_cap'
        detail=cg_get(f"/coins/{chosen['id']}",{'localization':'false','tickers':'false','market_data':'true','community_data':'false','developer_data':'false','sparkline':'false'}) or {}
        cats=detail.get('categories') or []
        country=(detail.get('country_origin') or '').strip() or 'Unknown/global'
        meta[market]={'coin_id':chosen['id'],'match_quality':quality,'country':country,'sector':simplify_sector(cats),'categories':' | '.join(cats[:12]),'current_market_cap_krw':chosen.get('market_cap')}

    out=[]
    for i,r in df.iterrows():
        m=meta.get(r.market,{})
        event_cap=historical_cap(m.get('coin_id'),r.day_kst) if m.get('coin_id') else np.nan
        z=r.to_dict(); z.update(m); z['event_market_cap_krw']=event_cap; z['event_market_cap_bucket']=cap_bucket(event_cap)
        z['pre30m_value_to_market_cap_pct']=(float(r.pre_value_30m_krw)/event_cap*100) if pd.notna(event_cap) and event_cap>0 else np.nan
        out.append(z)
        if (i+1)%50==0:print('enrich',i+1,'/',len(df),flush=True)
    e=pd.DataFrame(out)
    e.to_csv(OUT/'upbit_9am_realized_top5_enriched.csv',index=False)

    profile=(e.groupby(['event_market_cap_bucket','country','sector'],dropna=False).agg(
        samples=('market','size'),top1_count=('rank_9am',lambda s:int((s==1).sum())),
        avg_rank=('rank_9am','mean'),avg_max_return=('post_max_60m','mean'),
        avg_pre30m_value_to_cap_pct=('pre30m_value_to_market_cap_pct','mean'),
        avg_value5_ratio=('value5_ratio','mean'),avg_value30_ratio=('value30_ratio','mean')
    ).reset_index().sort_values(['samples','top1_count'],ascending=False))
    profile.to_csv(OUT/'upbit_9am_top5_profile_by_cap_country_sector.csv',index=False)

    sector=(e.groupby('sector',dropna=False).agg(samples=('market','size'),top1_count=('rank_9am',lambda s:int((s==1).sum())),avg_max_return=('post_max_60m','mean')).reset_index().sort_values('samples',ascending=False))
    sector.to_csv(OUT/'upbit_9am_top5_sector_summary.csv',index=False)
    country=(e.groupby('country',dropna=False).agg(samples=('market','size'),top1_count=('rank_9am',lambda s:int((s==1).sum())),avg_max_return=('post_max_60m','mean')).reset_index().sort_values('samples',ascending=False))
    country.to_csv(OUT/'upbit_9am_top5_country_summary.csv',index=False)
    cap=(e.groupby('event_market_cap_bucket',dropna=False).agg(samples=('market','size'),top1_count=('rank_9am',lambda s:int((s==1).sum())),avg_max_return=('post_max_60m','mean'),avg_value_to_cap_pct=('pre30m_value_to_market_cap_pct','mean')).reset_index().sort_values('samples',ascending=False))
    cap.to_csv(OUT/'upbit_9am_top5_market_cap_summary.csv',index=False)
    print('enriched rows',len(e),flush=True)

if __name__=='__main__':main()
