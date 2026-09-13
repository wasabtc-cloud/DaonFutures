import time
import math
import requests
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
from datetime import datetime, timedelta, timezone

BASE = 'https://api.upbit.com/v1'
FEE = 0.0005
SLIPPAGE = 0.0003
START_CAPITAL = 100000.0
DAYS = 365
TOP_DAILY = 20
MAX_CANDIDATES = 30
SESSION = requests.Session()
SESSION.headers.update({'User-Agent': 'DaonFutures-Upbit-Backtest/1.0'})


def get_json(path, params=None, tries=8):
    url = BASE + path
    for i in range(tries):
        r = SESSION.get(url, params=params, timeout=30)
        if r.status_code == 200:
            time.sleep(0.13)
            return r.json()
        if r.status_code == 429:
            time.sleep(min(5, 0.6 * (i + 1)))
            continue
        if r.status_code >= 500:
            time.sleep(min(5, 0.8 * (i + 1)))
            continue
        raise RuntimeError(f'HTTP {r.status_code} {url}: {r.text[:200]}')
    raise RuntimeError(f'Failed after retries: {url}')


def fetch_candles(market, unit, start, end):
    # Upbit returns newest first; walk backwards in chunks of 200.
    rows = []
    cursor = end
    path = f'/candles/minutes/{unit}'
    while cursor > start:
        js = get_json(path, {'market': market, 'to': cursor.strftime('%Y-%m-%dT%H:%M:%SZ'), 'count': 200})
        if not js:
            break
        rows.extend(js)
        oldest = pd.to_datetime(js[-1]['candle_date_time_utc'], utc=True).to_pydatetime()
        nxt = oldest - timedelta(seconds=1)
        if nxt >= cursor:
            break
        cursor = nxt
        if oldest <= start:
            break
    if not rows:
        return pd.DataFrame()
    df = pd.DataFrame(rows)
    df['ts'] = pd.to_datetime(df['candle_date_time_utc'], utc=True)
    df = df[(df['ts'] >= pd.Timestamp(start)) & (df['ts'] <= pd.Timestamp(end))]
    df = df.sort_values('ts').drop_duplicates('ts').set_index('ts')
    return df.rename(columns={
        'opening_price':'open','high_price':'high','low_price':'low','trade_price':'close',
        'candle_acc_trade_volume':'volume','candle_acc_trade_price':'value'
    })[['open','high','low','close','volume','value']].astype(float)


def fetch_days(market, start, end):
    rows = []
    cursor = end
    while cursor > start:
        js = get_json('/candles/days', {'market': market, 'to': cursor.strftime('%Y-%m-%dT%H:%M:%SZ'), 'count': 200})
        if not js:
            break
        rows.extend(js)
        oldest = pd.to_datetime(js[-1]['candle_date_time_utc'], utc=True).to_pydatetime()
        cursor = oldest - timedelta(seconds=1)
        if oldest <= start:
            break
    if not rows:
        return pd.DataFrame()
    df = pd.DataFrame(rows)
    df['ts'] = pd.to_datetime(df['candle_date_time_utc'], utc=True)
    df = df[(df['ts'] >= pd.Timestamp(start)) & (df['ts'] <= pd.Timestamp(end))]
    df = df.sort_values('ts').drop_duplicates('ts').set_index('ts')
    return df[['trade_price','candle_acc_trade_price']].rename(columns={'trade_price':'close','candle_acc_trade_price':'value'}).astype(float)


def ema(s, n):
    return s.ewm(span=n, adjust=False).mean()


def atr(df, n=14):
    pc = df['close'].shift(1)
    tr = pd.concat([(df['high']-df['low']).abs(), (df['high']-pc).abs(), (df['low']-pc).abs()], axis=1).max(axis=1)
    return tr.ewm(alpha=1/n, adjust=False).mean()


def build_features(df15):
    d = df15.copy()
    d['ema20'] = ema(d['close'], 20)
    d['atr14'] = atr(d, 14)
    d['prior20_high'] = d['high'].rolling(20).max().shift(1)
    d['value_ma20'] = d['value'].rolling(20).mean().shift(1)
    d['value_ratio'] = d['value'] / d['value_ma20']
    d['mom_1h'] = d['close'].pct_change(4)
    d['green'] = d['close'] > d['open']
    d['breakout'] = (d['close'] > d['prior20_high']) & (d['value_ratio'] >= 1.5) & (d['mom_1h'] > 0)

    # 4h trend made only from completed 15m bars, then shifted one 4h bar to avoid lookahead.
    h4 = d[['open','high','low','close','volume','value']].resample('4h').agg({
        'open':'first','high':'max','low':'min','close':'last','volume':'sum','value':'sum'
    }).dropna()
    h4['ema20_4h'] = ema(h4['close'], 20)
    h4['ema50_4h'] = ema(h4['close'], 50)
    h4['ema200_4h'] = ema(h4['close'], 200)
    h4['trend_ok'] = (h4['close'] > h4['ema200_4h']) & (h4['ema20_4h'] > h4['ema50_4h'])
    h4 = h4[['trend_ok']].shift(1)
    d['trend_ok'] = h4['trend_ok'].reindex(d.index, method='ffill').fillna(False)
    return d


def main():
    end = datetime.now(timezone.utc).replace(second=0, microsecond=0)
    start = end - timedelta(days=DAYS)
    warmup = start - timedelta(days=40)

    markets = get_json('/market/all', {'is_details':'false'})
    krw = sorted([x['market'] for x in markets if x['market'].startswith('KRW-')])
    print(f'KRW markets: {len(krw)}')

    # Phase 1: cheap daily scan. Universe for day D is based on D-1 turnover only.
    daily = {}
    freq = {}
    for idx, m in enumerate(krw, 1):
        try:
            dd = fetch_days(m, start - timedelta(days=8), end)
            if len(dd) >= 10:
                daily[m] = dd
        except Exception as e:
            print('daily skip', m, e)
        if idx % 20 == 0:
            print('daily', idx, '/', len(krw))

    all_dates = sorted(set().union(*[set(x.index.floor('D')) for x in daily.values()])) if daily else []
    daily_universe = {}
    for day in all_dates:
        if day < pd.Timestamp(start).floor('D'):
            continue
        prev = day - pd.Timedelta(days=1)
        vals = []
        for m, dd in daily.items():
            hit = dd[dd.index.floor('D') == prev]
            if len(hit):
                vals.append((m, float(hit.iloc[-1]['value'])))
        vals.sort(key=lambda x: x[1], reverse=True)
        picks = [m for m, _ in vals[:TOP_DAILY]]
        daily_universe[day] = set(picks)
        for m in picks:
            freq[m] = freq.get(m, 0) + 1

    candidates = [m for m, _ in sorted(freq.items(), key=lambda kv: kv[1], reverse=True)[:MAX_CANDIDATES]]
    print('Candidates:', candidates)

    # Phase 2: 15m data only for the most persistently liquid names.
    data = {}
    for idx, m in enumerate(candidates, 1):
        try:
            df = fetch_candles(m, 15, warmup, end)
            if len(df) > 1000:
                data[m] = build_features(df)
                print('15m', idx, '/', len(candidates), m, len(df))
        except Exception as e:
            print('15m skip', m, e)

    # Generate breakout->retest candidates. Retest must occur within next 6 bars.
    entries = []
    for m, d in data.items():
        idxs = np.flatnonzero((d['breakout'] & d['trend_ok']).fillna(False).values)
        for i in idxs:
            if i + 2 >= len(d):
                continue
            level = float(d.iloc[i]['prior20_high'])
            # Avoid chasing huge breakout candles > 6%.
            if float(d.iloc[i]['close'] / d.iloc[i]['open'] - 1) > 0.06:
                continue
            for j in range(i+1, min(i+7, len(d)-1)):
                r = d.iloc[j]
                touched = r['low'] <= level * 1.003
                held = r['close'] >= level and bool(r['green'])
                if touched and held:
                    nxt = d.iloc[j+1]
                    day = nxt.name.floor('D')
                    if m not in daily_universe.get(day, set()):
                        break
                    score = float(r['value_ratio']) + max(0.0, float(r['mom_1h']) * 20.0)
                    stop = min(float(r['low']) * 0.998, float(nxt['open']) - 1.5 * float(r['atr14']))
                    if stop <= 0 or stop >= float(nxt['open']):
                        break
                    entries.append({'time': nxt.name, 'market': m, 'score': score, 'stop': stop})
                    break

    entries = pd.DataFrame(entries)
    if entries.empty:
        raise RuntimeError('No entries generated')
    entries = entries.sort_values(['time','score'], ascending=[True,False])
    grouped = {t:g for t,g in entries.groupby('time')}

    # Event-driven portfolio: one coin at a time, 100% capital allocated, stop limits account loss.
    capital = START_CAPITAL
    peak = capital
    max_dd = 0.0
    trades = []
    equity_curve = []
    position = None
    timeline = sorted(set().union(*[set(d.loc[pd.Timestamp(start):].index) for d in data.values()]))

    for t in timeline:
        # Manage open trade using its own candle.
        if position is not None:
            m = position['market']
            d = data[m]
            if t in d.index:
                bar = d.loc[t]
                exit_price = None
                reason = None
                # Same-bar conservative priority: stop before target.
                if bar['low'] <= position['stop']:
                    exit_price = position['stop'] * (1 - SLIPPAGE)
                    reason = 'stop'
                else:
                    tp1 = position['entry'] * 1.03
                    if not position['half_done'] and bar['high'] >= tp1:
                        sell = tp1 * (1 - SLIPPAGE)
                        gross = position['qty'] * 0.5 * sell
                        capital += gross * (1 - FEE)
                        position['qty'] *= 0.5
                        position['half_done'] = True
                        position['stop'] = max(position['stop'], position['entry'])
                    # EMA20 trailing exit for runner, only on close; executed at close with slippage.
                    if position is not None and position['half_done'] and bar['close'] < bar['ema20']:
                        exit_price = float(bar['close']) * (1 - SLIPPAGE)
                        reason = 'ema20'
                if exit_price is not None:
                    proceeds = position['qty'] * exit_price * (1 - FEE)
                    capital += proceeds
                    pnl = capital - position['capital_before']
                    ret = pnl / position['capital_before']
                    trades.append({
                        'market':m,'entry_time':position['time'],'exit_time':t,'entry':position['entry'],
                        'exit':exit_price,'return_pct':ret*100,'reason':reason
                    })
                    position = None

        # Open only when flat; choose highest score at that timestamp.
        if position is None and t in grouped:
            for _, sig in grouped[t].iterrows():
                m = sig['market']
                if m not in data or t not in data[m].index:
                    continue
                raw = float(data[m].loc[t, 'open'])
                entry = raw * (1 + SLIPPAGE)
                stop = float(sig['stop'])
                # Reject absurdly wide or tiny stops.
                risk_pct = (entry - stop) / entry
                if risk_pct < 0.003 or risk_pct > 0.08:
                    continue
                before = capital
                buy_cash = capital
                qty = (buy_cash * (1 - FEE)) / entry
                capital = 0.0
                position = {'market':m,'time':t,'entry':entry,'stop':stop,'qty':qty,
                            'half_done':False,'capital_before':before}
                break

        # Mark-to-market equity.
        eq = capital
        if position is not None:
            m = position['market']
            if t in data[m].index:
                eq += position['qty'] * float(data[m].loc[t,'close']) * (1 - FEE)
        peak = max(peak, eq)
        dd = (peak - eq) / peak if peak else 0
        max_dd = max(max_dd, dd)
        equity_curve.append((t, eq))

    if position is not None:
        m = position['market']
        last = data[m].iloc[-1]
        exit_price = float(last['close']) * (1 - SLIPPAGE)
        capital += position['qty'] * exit_price * (1 - FEE)
        pnl = capital - position['capital_before']
        trades.append({'market':m,'entry_time':position['time'],'exit_time':data[m].index[-1],
                       'entry':position['entry'],'exit':exit_price,
                       'return_pct':pnl/position['capital_before']*100,'reason':'end'})

    tr = pd.DataFrame(trades)
    wins = tr[tr['return_pct'] > 0] if len(tr) else tr
    losses = tr[tr['return_pct'] <= 0] if len(tr) else tr
    gross_win = wins['return_pct'].sum() if len(wins) else 0.0
    gross_loss = -losses['return_pct'].sum() if len(losses) else 0.0
    pf = gross_win / gross_loss if gross_loss > 0 else math.inf
    final = capital
    result = pd.DataFrame([{
        'strategy':'Upbit MoneyFlow Rotation v1',
        'period_days':DAYS,
        'start_capital_krw':START_CAPITAL,
        'final_capital_krw':round(final,2),
        'return_pct':round((final/START_CAPITAL-1)*100,4),
        'trades':len(tr),
        'win_rate_pct':round((len(wins)/len(tr)*100) if len(tr) else 0,4),
        'profit_factor':round(pf,4) if np.isfinite(pf) else 'inf',
        'max_drawdown_pct':round(max_dd*100,4),
        'candidate_markets':len(data),
        'daily_top_n':TOP_DAILY,
        'fee_each_fill_pct':FEE*100,
        'slippage_each_fill_pct':SLIPPAGE*100
    }])
    result.to_csv('backtest_results.csv', index=False)
    tr.to_csv('upbit_moneyflow_trades.csv', index=False)

    ec = pd.DataFrame(equity_curve, columns=['time','equity']).drop_duplicates('time').set_index('time')
    plt.figure(figsize=(12,5))
    plt.plot(ec.index, ec['equity'])
    plt.title('Upbit MoneyFlow Rotation v1 - 1Y Equity')
    plt.ylabel('KRW')
    plt.xlabel('Time')
    plt.tight_layout()
    plt.savefig('backtest_equity.png', dpi=150)
    print(result.to_string(index=False))
    print('Top trades:')
    if len(tr): print(tr.sort_values('return_pct', ascending=False).head(10).to_string(index=False))


if __name__ == '__main__':
    main()
