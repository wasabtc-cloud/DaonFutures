import io, zipfile, urllib.request
from datetime import date, timedelta
import pandas as pd
import numpy as np

START = pd.Timestamp('2023-09-13', tz='UTC')
END = pd.Timestamp('2026-09-13', tz='UTC')
SYMBOLS = ['BTCUSDT', 'ETHUSDT']
INTERVALS = ['5m', '15m']
ADX_LEVELS = [20, 25]
FEE = 0.0005
SLIPPAGE = 0.0002
TP1 = 0.02
ATR_STOP = 1.5
ATR_TRAIL = 3.0
INITIAL_EQUITY = 100.0


def read_zip(url):
    try:
        with urllib.request.urlopen(url, timeout=60) as r:
            raw = r.read()
        with zipfile.ZipFile(io.BytesIO(raw)) as z:
            return pd.read_csv(z.open(z.namelist()[0]), header=None)
    except Exception as exc:
        print('skip', url, type(exc).__name__, flush=True)
        return pd.DataFrame()


def month_iter(start_y, start_m, end_y, end_m):
    y, m = start_y, start_m
    while (y, m) <= (end_y, end_m):
        yield y, m
        m += 1
        if m == 13:
            y += 1
            m = 1


def download(symbol, interval):
    parts = []
    # Monthly files through the last complete month before END.
    for y, m in month_iter(2023, 9, 2026, 8):
        url = f'https://data.binance.vision/data/futures/um/monthly/klines/{symbol}/{interval}/{symbol}-{interval}-{y}-{m:02d}.zip'
        x = read_zip(url)
        if not x.empty:
            parts.append(x)
    # Daily files for September 2026 through the last closed UTC day in the test.
    d = date(2026, 9, 1)
    while d < date(2026, 9, 13):
        url = f'https://data.binance.vision/data/futures/um/daily/klines/{symbol}/{interval}/{symbol}-{interval}-{d.isoformat()}.zip'
        x = read_zip(url)
        if not x.empty:
            parts.append(x)
        d += timedelta(days=1)
    if not parts:
        raise RuntimeError(f'No data downloaded for {symbol} {interval}')
    r = pd.concat(parts, ignore_index=True).iloc[:, :12]
    r.columns = ['time','open','high','low','close','volume','ct','qv','trades','tb','tq','ignore']
    for c in ['time','open','high','low','close','volume']:
        r[c] = pd.to_numeric(r[c], errors='coerce')
    r = r.dropna(subset=['time','open','high','low','close','volume'])
    raw_time = r['time'].astype('int64')
    unit = 'us' if raw_time.median() > 10**14 else 'ms'
    r['time'] = pd.to_datetime(raw_time, unit=unit, utc=True)
    r = r.drop_duplicates('time').set_index('time').sort_index()
    r = r.loc[(r.index >= START - pd.Timedelta(days=40)) & (r.index < END)]
    return r[['open','high','low','close','volume']]


def ema(s, n):
    return s.ewm(span=n, adjust=False).mean()


def rsi(s, n=14):
    delta = s.diff()
    up = delta.clip(lower=0).ewm(alpha=1/n, adjust=False).mean()
    dn = (-delta.clip(upper=0)).ewm(alpha=1/n, adjust=False).mean()
    rs = up / dn.replace(0, np.nan)
    return (100 - 100/(1 + rs)).fillna(50)


def atr(d, n=14):
    pc = d.close.shift()
    tr = pd.concat([(d.high-d.low), (d.high-pc).abs(), (d.low-pc).abs()], axis=1).max(axis=1)
    return tr.ewm(alpha=1/n, adjust=False).mean()


def adx(d, n=14):
    up = d.high.diff()
    down = -d.low.diff()
    plus_dm = pd.Series(np.where((up > down) & (up > 0), up, 0.0), index=d.index)
    minus_dm = pd.Series(np.where((down > up) & (down > 0), down, 0.0), index=d.index)
    a = atr(d, n)
    plus_di = 100 * plus_dm.ewm(alpha=1/n, adjust=False).mean() / a.replace(0, np.nan)
    minus_di = 100 * minus_dm.ewm(alpha=1/n, adjust=False).mean() / a.replace(0, np.nan)
    dx = 100 * (plus_di-minus_di).abs() / (plus_di+minus_di).replace(0, np.nan)
    return dx.ewm(alpha=1/n, adjust=False).mean()


def prepare(d):
    d = d.copy()
    d['ema9'] = ema(d.close, 9)
    d['ema21'] = ema(d.close, 21)
    d['rsi'] = rsi(d.close)
    d['adx'] = adx(d)
    d['atr'] = atr(d)
    d['vma20'] = d.volume.rolling(20).mean()

    h4 = d.resample('4h', label='right', closed='right').agg({
        'open':'first','high':'max','low':'min','close':'last','volume':'sum'
    }).dropna()
    h4['ema200'] = ema(h4.close, 200)
    d = d.join(h4[['ema200']].rename(columns={'ema200':'h4ema200'})).ffill()
    return d


def signals(d, adx_level):
    cross_up = (d.ema9 > d.ema21) & (d.ema9.shift(1) <= d.ema21.shift(1))
    cross_dn = (d.ema9 < d.ema21) & (d.ema9.shift(1) >= d.ema21.shift(1))
    vol_ok = d.volume >= d.vma20
    long_sig = cross_up & (d.rsi > 50) & (d.adx >= adx_level) & vol_ok & (d.close > d.h4ema200)
    short_sig = cross_dn & (d.rsi < 50) & (d.adx >= adx_level) & vol_ok & (d.close < d.h4ema200)
    return pd.Series(np.where(long_sig, 1, np.where(short_sig, -1, 0)), index=d.index)


def backtest(d, sig):
    equity = INITIAL_EQUITY
    peak = equity
    max_dd = 0.0
    trades = []
    i = 0
    n = len(d)

    while i < n-1 and equity > 0.01:
        side = int(sig.iloc[i])
        if side == 0 or not np.isfinite(d.atr.iloc[i]):
            i += 1
            continue

        entry = d.close.iloc[i] * (1 + SLIPPAGE*side)
        initial_stop = entry - side * ATR_STOP * d.atr.iloc[i]
        tp = entry * (1 + side*TP1)
        stop = initial_stop
        partial = False
        ret = 0.0
        fees = FEE
        j = i + 1
        exit_reason = 'eod'

        while j < n:
            lo, hi = d.low.iloc[j], d.high.iloc[j]
            hit_stop = lo <= stop if side == 1 else hi >= stop
            hit_tp = hi >= tp if side == 1 else lo <= tp

            # Conservative assumption when stop and target are both touched in one candle.
            if not partial:
                if hit_stop:
                    fill = stop * (1 - SLIPPAGE*side)
                    ret = side * (fill/entry - 1)
                    fees += FEE
                    exit_reason = 'stop'
                    break
                if hit_tp:
                    fill = tp * (1 - SLIPPAGE*side)
                    ret += 0.5 * side * (fill/entry - 1)
                    fees += 0.5 * FEE
                    partial = True
                    stop = entry
                    exit_reason = 'runner'
                    j += 1
                    continue
            else:
                a = d.atr.iloc[j]
                if side == 1:
                    trail_candidate = d.close.iloc[j] - ATR_TRAIL*a
                    stop = max(stop, trail_candidate)
                    hit_stop = lo <= stop
                else:
                    trail_candidate = d.close.iloc[j] + ATR_TRAIL*a
                    stop = min(stop, trail_candidate)
                    hit_stop = hi >= stop
                if hit_stop:
                    fill = stop * (1 - SLIPPAGE*side)
                    ret += 0.5 * side * (fill/entry - 1)
                    fees += 0.5 * FEE
                    exit_reason = 'trail'
                    break
            j += 1

        if j >= n:
            fill = d.close.iloc[-1] * (1 - SLIPPAGE*side)
            remaining = 0.5 if partial else 1.0
            ret += remaining * side * (fill/entry - 1)
            fees += remaining * FEE
            j = n-1
            exit_reason = 'eod'

        net_ret = ret - fees
        before = equity
        equity *= max(0.0, 1 + net_ret)
        pnl = equity - before
        peak = max(peak, equity)
        max_dd = max(max_dd, (peak-equity)/peak if peak else 0)
        trades.append({
            'entry_time': d.index[i], 'exit_time': d.index[j], 'side': 'LONG' if side==1 else 'SHORT',
            'net_return_pct': net_ret*100, 'pnl': pnl, 'equity': equity, 'exit_reason': exit_reason
        })
        i = j + 1

    t = pd.DataFrame(trades)
    if t.empty:
        return {'FinalEquity':equity,'ReturnPct':equity-100,'Trades':0,'WinRatePct':0,'PF':0,'MDDPct':0,'LongTrades':0,'ShortTrades':0}, t
    wins = (t.pnl > 0).sum()
    gross_profit = t.loc[t.pnl > 0, 'pnl'].sum()
    gross_loss = -t.loc[t.pnl < 0, 'pnl'].sum()
    pf = gross_profit/gross_loss if gross_loss > 0 else np.inf
    stats = {
        'FinalEquity': equity,
        'ReturnPct': (equity/INITIAL_EQUITY-1)*100,
        'Trades': len(t),
        'WinRatePct': wins/len(t)*100,
        'PF': pf,
        'MDDPct': max_dd*100,
        'LongTrades': (t.side=='LONG').sum(),
        'ShortTrades': (t.side=='SHORT').sum(),
    }
    return stats, t


def main():
    rows = []
    all_trades = []
    for symbol in SYMBOLS:
        for interval in INTERVALS:
            print(f'\n=== Downloading {symbol} {interval} ===', flush=True)
            d = prepare(download(symbol, interval))
            d = d.loc[(d.index >= START) & (d.index < END)].copy()
            print(f'{symbol} {interval}: {len(d):,} candles', flush=True)
            for level in ADX_LEVELS:
                sig = signals(d, level)
                stats, trades = backtest(d, sig)
                row = {'Symbol':symbol, 'Interval':interval, 'ADX':level, **stats}
                rows.append(row)
                if not trades.empty:
                    trades.insert(0, 'ADX', level)
                    trades.insert(0, 'Interval', interval)
                    trades.insert(0, 'Symbol', symbol)
                    all_trades.append(trades)
                print(row, flush=True)

    out = pd.DataFrame(rows)
    out = out.sort_values(['PF','ReturnPct'], ascending=False)
    out.to_csv('backtest_3y_summary.csv', index=False)
    if all_trades:
        pd.concat(all_trades, ignore_index=True).to_csv('backtest_3y_trades.csv', index=False)
    print('\n=== 3Y SUMMARY ===', flush=True)
    print(out.to_string(index=False), flush=True)


if __name__ == '__main__':
    main()
