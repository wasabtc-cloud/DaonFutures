import time
import requests
import numpy as np
import pandas as pd

BASE = 'https://api.upbit.com/v1'
FEE = 0.0005
SLIP = 0.0003
STOP_TYPE = 'SWING20'
HORIZON_MINUTES = 360
MAX_RPS = 8

_last_calls = []

def throttle():
    global _last_calls
    while True:
        now = time.monotonic()
        _last_calls = [x for x in _last_calls if now - x < 1.0]
        if len(_last_calls) < MAX_RPS:
            _last_calls.append(now)
            return
        time.sleep(0.05)


def get(path, params=None, retries=5):
    for k in range(retries):
        throttle()
        try:
            r = requests.get(BASE + path, params=params, timeout=25,
                             headers={'User-Agent':'DaonFutures-MinuteExitValidation'})
            if r.status_code == 429:
                time.sleep(0.5 * (k + 1))
                continue
            r.raise_for_status()
            return r.json()
        except Exception:
            if k == retries - 1:
                raise
            time.sleep(0.35 * (k + 1))


def fetch_path(market, entry_time):
    start = pd.Timestamp(entry_time)
    if start.tzinfo is None:
        start = start.tz_localize('UTC')
    else:
        start = start.tz_convert('UTC')
    end = start + pd.Timedelta(minutes=HORIZON_MINUTES + 25)
    rows, to = [], end
    for _ in range(4):
        js = get('/candles/minutes/1', {
            'market': market,
            'count': 200,
            'to': to.strftime('%Y-%m-%dT%H:%M:%SZ')
        })
        if not js:
            break
        rows += js
        oldest = pd.Timestamp(js[-1]['candle_date_time_utc'], tz='UTC')
        if oldest <= start - pd.Timedelta(minutes=25):
            break
        to = oldest - pd.Timedelta(seconds=1)
    if not rows:
        return pd.DataFrame()
    d = pd.DataFrame(rows)
    d['time'] = pd.to_datetime(d['candle_date_time_utc'], utc=True)
    d = d.drop_duplicates('time').set_index('time').sort_index()
    out = pd.DataFrame(index=d.index)
    out['open'] = pd.to_numeric(d['opening_price'])
    out['high'] = pd.to_numeric(d['high_price'])
    out['low'] = pd.to_numeric(d['low_price'])
    out['close'] = pd.to_numeric(d['trade_price'])
    return out.loc[(out.index >= start - pd.Timedelta(minutes=25)) &
                   (out.index <= start + pd.Timedelta(minutes=HORIZON_MINUTES))]


def max_drawdown_from_r(rvals, risk_fraction=0.01):
    eq = 100.0
    peak = eq
    mdd = 0.0
    for r in rvals:
        eq *= max(0.0, 1.0 + risk_fraction * float(r))
        peak = max(peak, eq)
        if peak > 0:
            mdd = max(mdd, (peak - eq) / peak)
    return mdd * 100.0, eq


def loss_streak(rvals):
    best = cur = 0
    for r in rvals:
        if r < 0:
            cur += 1
            best = max(best, cur)
        else:
            cur = 0
    return best


def simulate(path, entry, initial_stop, mode):
    risk = entry - initial_stop
    if risk <= 0 or path.empty:
        return np.nan, 'invalid'
    tp2 = entry + 2.0 * risk
    tp3 = entry + 3.0 * risk
    active_stop = initial_stop
    partial = False
    realized_r = 0.0
    remaining = 1.0
    lows_hist = []

    for ts, bar in path.iterrows():
        lo = float(bar.low)
        hi = float(bar.high)
        lows_hist.append(lo)

        # Conservative intrabar ordering: stop before target.
        if lo <= active_stop:
            stop_fill = active_stop * (1 - SLIP)
            stop_r = (stop_fill - entry) / risk
            realized_r += remaining * stop_r
            # approximate two-sided fees in R on the remaining piece
            realized_r -= remaining * ((entry * FEE + stop_fill * FEE) / risk)
            return realized_r, 'stop_or_trail'

        if mode == 'FULL_3R':
            if hi >= tp3:
                fill = tp3 * (1 - SLIP)
                r = (fill - entry) / risk
                r -= (entry * FEE + fill * FEE) / risk
                return r, '3R'
            continue

        if not partial and hi >= tp2:
            frac = 0.30 if mode == 'TP2R_30_TRAIL_SWING20' else 0.50
            fill = tp2 * (1 - SLIP)
            piece_r = (fill - entry) / risk
            piece_r -= (entry * FEE + fill * FEE) / risk
            realized_r += frac * piece_r
            remaining = 1.0 - frac
            partial = True
            active_stop = max(active_stop, entry)
            continue

        if partial:
            # Trail using only completed bars: prior 20 one-minute lows, never below breakeven.
            if len(lows_hist) >= 21:
                prior20_low = min(lows_hist[-21:-1])
                active_stop = max(active_stop, prior20_low)
            if hi >= tp3:
                fill = tp3 * (1 - SLIP)
                piece_r = (fill - entry) / risk
                piece_r -= (entry * FEE + fill * FEE) / risk
                realized_r += remaining * piece_r
                return realized_r, 'runner_3R'

    # Close at the last available 1m close after six-hour evaluation window.
    fill = float(path.close.iloc[-1]) * (1 - SLIP)
    piece_r = (fill - entry) / risk
    piece_r -= (entry * FEE + fill * FEE) / risk
    realized_r += remaining * piece_r
    return realized_r, 'time_exit'


def main():
    tr = pd.read_csv('entry_stop_trades.csv')
    g = tr[tr['stop_type'].eq(STOP_TYPE)].copy()
    if g.empty:
        raise RuntimeError(f'No {STOP_TYPE} rows in entry_stop_trades.csv')
    g['entry_time'] = pd.to_datetime(g['entry_time'], utc=True)
    g = g.sort_values('entry_time').reset_index(drop=True)

    modes = ['FULL_3R', 'TP2R_30_TRAIL_SWING20', 'TP2R_50_TRAIL_SWING20']
    detail = []
    total = len(g)
    for idx, row in g.iterrows():
        print(f'fetch {idx+1}/{total} {row.market} {row.entry_time}', flush=True)
        p = fetch_path(row.market, row.entry_time)
        p = p.loc[p.index >= row.entry_time]
        if p.empty:
            continue
        for mode in modes:
            r, reason = simulate(p, float(row.entry), float(row.stop), mode)
            detail.append({
                'market': row.market,
                'label': int(row.label),
                'entry_time': row.entry_time,
                'strategy': mode,
                'risk_pct': float(row.risk_pct),
                'result_r': r,
                'exit_reason': reason,
            })

    d = pd.DataFrame(detail).dropna(subset=['result_r'])
    if d.empty:
        raise RuntimeError('No minute validation results produced')

    rows = []
    for mode, gp in d.groupby('strategy'):
        gp = gp.sort_values('entry_time')
        r = gp.result_r.astype(float)
        gross_profit = r[r > 0].sum()
        gross_loss = -r[r < 0].sum()
        pf = gross_profit / gross_loss if gross_loss > 0 else np.inf
        mdd, ending_equity = max_drawdown_from_r(r.values)
        rows.append({
            'strategy': mode,
            'trades': len(gp),
            'win_rate_pct': (r > 0).mean() * 100,
            'avg_r': r.mean(),
            'median_r': r.median(),
            'profit_factor_r': pf,
            'mdd_pct_at_1pct_risk': mdd,
            'ending_equity_at_1pct_risk': ending_equity,
            'max_consecutive_losses': loss_streak(r.values),
            'positive_2r_plus_pct': (r >= 2.0).mean() * 100,
        })
    s = pd.DataFrame(rows).sort_values(['profit_factor_r','avg_r'], ascending=False).reset_index(drop=True)
    s['rank'] = np.arange(1, len(s) + 1)
    s.to_csv('exit_minute_validation_summary.csv', index=False)
    d.to_csv('exit_minute_validation_trades.csv', index=False)

    print('\nMINUTE-BY-MINUTE EXIT VALIDATION (SWING20)\n', flush=True)
    print(s.to_string(index=False), flush=True)
    print('\nRULES:', flush=True)
    print('- Entry/initial stop come from the frozen OOS SWING20 rows.', flush=True)
    print('- Conservative same-bar ordering: stop before target.', flush=True)
    print('- Partial-exit modes take 30% or 50% at 2R, move stop to breakeven, then trail by prior 20 completed 1m lows.', flush=True)
    print('- Runner is capped at 3R for an apples-to-apples comparison.', flush=True)
    print('- MDD/equity are research sequence metrics assuming 1% equity risk per trade, not natural-prevalence portfolio PnL.', flush=True)


if __name__ == '__main__':
    main()
