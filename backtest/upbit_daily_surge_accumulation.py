"""Daily Surge + Accumulation research scanner for Upbit KRW markets.

Research/backtest only. No orders are placed.

Design:
- 5-minute candles for a broad all-day scan.
- Features use only information available at each detection timestamp.
- Future +5/+10/+15/+20% moves are labels only, never inputs.
- Two transparent scores are reported:
  * spike_score: sudden short-term transaction-value acceleration + momentum
  * accumulation_score: persistent multi-hour value inflow while price remains relatively contained
- Combined score ranks practical candidates.
"""
from __future__ import annotations

import time
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd
import requests

BASE = 'https://api.upbit.com/v1'
OUT = Path('results_daily_surge')
OUT.mkdir(exist_ok=True)
DAYS = 60
TOP_MARKETS = 20
BAR_MINUTES = 5
STEP_BARS = 3              # score every 15 minutes
FORWARD_BARS = 72          # next 6 hours
THRESHOLDS = (0.05, 0.10, 0.15, 0.20)


def get(path, params=None, retries=6):
    for k in range(retries):
        try:
            r = requests.get(
                BASE + path,
                params=params,
                timeout=30,
                headers={'User-Agent': 'DaonFutures-Daily-Surge-Accumulation'},
            )
            if r.status_code == 429:
                time.sleep(0.35 * (k + 1))
                continue
            r.raise_for_status()
            return r.json()
        except Exception:
            if k == retries - 1:
                raise
            time.sleep(0.5 * (k + 1))


def markets():
    return [
        x['market'] for x in get('/market/all', {'is_details': 'false'})
        if x['market'].startswith('KRW-')
    ]


def candles_5m(market, start, end):
    rows = []
    to = end + pd.Timedelta(minutes=BAR_MINUTES)
    while to > start:
        js = get(
            f'/candles/minutes/{BAR_MINUTES}',
            {'market': market, 'count': 200, 'to': to.strftime('%Y-%m-%dT%H:%M:%SZ')},
        )
        if not js:
            break
        rows += js
        old = pd.Timestamp(js[-1]['candle_date_time_utc'], tz='UTC')
        if old <= start:
            break
        to = old - pd.Timedelta(seconds=1)
    if not rows:
        return pd.DataFrame()
    d = pd.DataFrame(rows)
    d['time'] = pd.to_datetime(d.candle_date_time_utc, utc=True)
    d = d.drop_duplicates('time').set_index('time').sort_index().loc[start:end]
    out = pd.DataFrame(index=d.index)
    for a, b in [
        ('open', 'opening_price'), ('high', 'high_price'), ('low', 'low_price'),
        ('close', 'trade_price'), ('value', 'candle_acc_trade_price'),
        ('volume', 'candle_acc_trade_volume'),
    ]:
        out[a] = pd.to_numeric(d[b])
    return out


def daily_value_rank(ms, anchor):
    vals = []
    for i, m in enumerate(ms, 1):
        try:
            js = get('/candles/days', {'market': m, 'count': 20, 'to': anchor.strftime('%Y-%m-%dT%H:%M:%SZ')})
            if js:
                vals.append((m, float(np.mean([x['candle_acc_trade_price'] for x in js]))))
        except Exception:
            pass
        if i % 50 == 0:
            print('rank', i, '/', len(ms), flush=True)
    return [m for m, _ in sorted(vals, key=lambda z: z[1], reverse=True)[:TOP_MARKETS]]


def rolling_features(d):
    x = d.copy()
    # transaction-value sums: 1h/3h/6h/12h/24h on 5-minute bars
    for name, n in [('1h', 12), ('3h', 36), ('6h', 72), ('12h', 144), ('24h', 288)]:
        x[f'value_{name}'] = x.value.rolling(n).sum()
        x[f'ret_{name}'] = x.close / x.close.shift(n) - 1

    x['value_15m'] = x.value.rolling(3).sum()
    x['prev_value_15m'] = x.value.shift(3).rolling(3).sum()
    x['value_accel_15m'] = x['value_15m'] / (x['prev_value_15m'] + 1e-12)

    # Baselines use prior information only.
    hourly = x.value.rolling(12).sum()
    x['value1h_vs_24h_med'] = hourly / (hourly.shift(1).rolling(288).median() + 1e-12)
    x['value3h_vs_prev12h'] = x['value_3h'] / ((x.value.shift(36).rolling(144).sum() / 4.0) + 1e-12)
    x['value6h_vs_prev24h'] = x['value_6h'] / ((x.value.shift(72).rolling(288).sum() / 4.0) + 1e-12)

    # Persistence: fraction of recent 3h bars above trailing 24h median value.
    baseline_bar = x.value.shift(1).rolling(288).median()
    x['persistent_inflow_3h'] = (x.value > baseline_bar).rolling(36).mean()

    # Volatility compression and breakout location, all trailing/current only.
    tr = pd.concat([
        x.high - x.low,
        (x.high - x.close.shift(1)).abs(),
        (x.low - x.close.shift(1)).abs(),
    ], axis=1).max(axis=1)
    x['atr_1h_pct'] = tr.rolling(12).mean() / (x.close + 1e-12)
    x['range_3h_pct'] = (x.high.rolling(36).max() - x.low.rolling(36).min()) / (x.close + 1e-12)
    x['breakout_1h'] = x.close / (x.high.shift(1).rolling(12).max() + 1e-12) - 1
    return x


def build_samples(market, raw):
    if len(raw) < 400:
        return []
    x = rolling_features(raw)
    rows = []
    # Need 24h history and 6h future.
    for i in range(320, len(x) - FORWARD_BARS, STEP_BARS):
        r = x.iloc[i]
        needed = [
            'value_accel_15m', 'value1h_vs_24h_med', 'value3h_vs_prev12h',
            'value6h_vs_prev24h', 'persistent_inflow_3h', 'ret_1h', 'ret_3h',
            'ret_6h', 'atr_1h_pct', 'range_3h_pct', 'breakout_1h'
        ]
        if not np.isfinite(r[needed].astype(float)).all():
            continue
        future = x.iloc[i + 1:i + 1 + FORWARD_BARS]
        if future.empty:
            continue
        p = float(r.close)
        mfe = float(future.high.max() / p - 1)
        mae = float(future.low.min() / p - 1)

        # Sudden-flow detector.
        spike_score = (
            np.log1p(max(float(r.value_accel_15m), 0.0)) * 1.4 +
            np.log1p(max(float(r.value1h_vs_24h_med), 0.0)) * 1.0 +
            np.clip(float(r.ret_1h), -0.08, 0.08) * 8.0 +
            np.clip(float(r.breakout_1h), -0.05, 0.05) * 10.0
        )

        # Slow accumulation detector: sustained value growth is rewarded while excessive
        # price expansion is penalized, favoring 'money in before price runs'.
        price_penalty = max(abs(float(r.ret_6h)) - 0.02, 0.0) * 10.0
        accumulation_score = (
            np.log1p(max(float(r.value3h_vs_prev12h), 0.0)) * 1.0 +
            np.log1p(max(float(r.value6h_vs_prev24h), 0.0)) * 1.2 +
            float(r.persistent_inflow_3h) * 1.5 +
            np.log1p(max(float(r.value1h_vs_24h_med), 0.0)) * 0.6 -
            price_penalty -
            min(float(r.range_3h_pct), 0.20) * 1.5
        )
        combined_score = 0.55 * accumulation_score + 0.45 * spike_score

        row = {
            'time_utc': x.index[i].isoformat(),
            'time_kst': x.index[i].tz_convert('Asia/Seoul').isoformat(),
            'market': market,
            'price': p,
            'spike_score': float(spike_score),
            'accumulation_score': float(accumulation_score),
            'combined_score': float(combined_score),
            'value_accel_15m': float(r.value_accel_15m),
            'value1h_vs_24h_med': float(r.value1h_vs_24h_med),
            'value3h_vs_prev12h': float(r.value3h_vs_prev12h),
            'value6h_vs_prev24h': float(r.value6h_vs_prev24h),
            'persistent_inflow_3h': float(r.persistent_inflow_3h),
            'ret_1h': float(r.ret_1h),
            'ret_3h': float(r.ret_3h),
            'ret_6h': float(r.ret_6h),
            'atr_1h_pct': float(r.atr_1h_pct),
            'range_3h_pct': float(r.range_3h_pct),
            'breakout_1h': float(r.breakout_1h),
            'mfe_6h': mfe,
            'mae_6h': mae,
        }
        for th in THRESHOLDS:
            row[f'label_{int(th*100)}pct'] = int(mfe >= th)
        rows.append(row)
    return rows


def evaluate(df, score_col, label):
    rows = []
    base = float(df[label].mean())
    for q in (0.90, 0.95, 0.97, 0.99):
        th = float(df[score_col].quantile(q))
        s = df[df[score_col] >= th]
        if s.empty:
            continue
        rows.append({
            'score': score_col,
            'label': label,
            'quantile': q,
            'threshold': th,
            'signals': len(s),
            'hit_rate_pct': float(s[label].mean() * 100),
            'base_rate_pct': base * 100,
            'lift': float(s[label].mean() / (base + 1e-12)),
            'avg_mfe_6h_pct': float(s.mfe_6h.mean() * 100),
            'avg_mae_6h_pct': float(s.mae_6h.mean() * 100),
        })
    return rows


def main():
    end = pd.Timestamp(datetime.now(timezone.utc)).floor('5min')
    start = end - pd.Timedelta(days=DAYS + 2)
    universe = daily_value_rank(markets(), start)
    print('UNIVERSE', universe, flush=True)

    rows = []
    for ix, m in enumerate(universe, 1):
        print(f'DAILY {ix}/{len(universe)} {m}', flush=True)
        try:
            raw = candles_5m(m, start - pd.Timedelta(days=2), end)
            rows.extend(build_samples(m, raw))
        except Exception as e:
            print('skip', m, e, flush=True)

    df = pd.DataFrame(rows)
    if df.empty:
        raise RuntimeError('no daily surge samples')
    df.to_csv(OUT / 'daily_surge_samples.csv', index=False)

    metrics = []
    for score_col in ['spike_score', 'accumulation_score', 'combined_score']:
        for pct in (5, 10, 15, 20):
            metrics.extend(evaluate(df, score_col, f'label_{pct}pct'))
    metrics_df = pd.DataFrame(metrics)
    metrics_df.to_csv(OUT / 'daily_surge_metrics.csv', index=False)

    # Practical top-3 ranking each KST day from the combined score.
    df['day_kst'] = pd.to_datetime(df.time_kst).dt.strftime('%Y-%m-%d')
    top = (
        df.sort_values(['day_kst', 'combined_score'], ascending=[True, False])
          .groupby('day_kst')
          .head(3)
    )
    top.to_csv(OUT / 'daily_surge_top3_daily.csv', index=False)

    # First detection per market/day above the 97th percentile, useful for lead-time review.
    th97 = float(df.combined_score.quantile(0.97))
    first = (
        df[df.combined_score >= th97]
        .sort_values('time_utc')
        .groupby(['day_kst', 'market'])
        .head(1)
    )
    first.to_csv(OUT / 'daily_surge_first_detection.csv', index=False)
    print(metrics_df.to_string(index=False), flush=True)


if __name__ == '__main__':
    main()
