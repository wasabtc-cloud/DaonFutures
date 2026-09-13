import math
from datetime import datetime, timedelta, timezone
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt

from backtest.upbit_moneyflow_1y import get_json, fetch_candles, fetch_days, ema, atr

FEE = 0.0005
SLIPPAGE = 0.0003
START_CAPITAL = 100000.0
DAYS = 365
TOP_DAILY = 5
MAX_CANDIDATES = 35


def build_features(df15):
    d = df15.copy()
    d['ema20'] = ema(d['close'], 20)
    d['ema50'] = ema(d['close'], 50)
    d['atr14'] = atr(d, 14)
    d['prior20_high'] = d['high'].rolling(20).max().shift(1)
    d['value_ma20'] = d['value'].rolling(20).mean().shift(1)
    d['value_ma80'] = d['value'].rolling(80).mean().shift(1)
    d['value_ratio'] = d['value'] / d['value_ma20']
    d['flow_accel'] = d['value_ma20'] / d['value_ma80']
    d['mom_1h'] = d['close'].pct_change(4)
    d['green'] = d['close'] > d['open']
    d['bar_ret'] = d['close'] / d['open'] - 1

    # Strict money-flow breakout: large volume expansion, positive acceleration,
    # but exclude already-overheated moves.
    d['breakout'] = (
        (d['close'] > d['prior20_high']) &
        (d['value_ratio'] >= 2.0) &
        (d['flow_accel'] >= 1.10) &
        (d['mom_1h'] > 0) & (d['mom_1h'] < 0.05) &
        (d['bar_ret'] < 0.03)
    )

    h4 = d[['open','high','low','close','volume','value']].resample('4h').agg({
        'open':'first','high':'max','low':'min','close':'last','volume':'sum','value':'sum'
    }).dropna()
    h4['ema20'] = ema(h4['close'], 20)
    h4['ema50'] = ema(h4['close'], 50)
    h4['ema200'] = ema(h4['close'], 200)
    h4['ema20_prev'] = h4['ema20'].shift(1)
    h4['trend_ok'] = (
        (h4['close'] > h4['ema200']) &
        (h4['close'] > h4['ema20']) &
        (h4['ema20'] > h4['ema50']) &
        (h4['ema20'] > h4['ema20_prev'])
    )
    d['trend_ok'] = h4[['trend_ok']].shift(1)['trend_ok'].reindex(d.index, method='ffill').fillna(False)
    return d


def build_btc_filter(btc):
    d = btc.copy()
    h4 = d[['open','high','low','close']].resample('4h').agg({'open':'first','high':'max','low':'min','close':'last'}).dropna()
    h4['ema20'] = ema(h4['close'], 20)
    h4['ema50'] = ema(h4['close'], 50)
    h4['ema200'] = ema(h4['close'], 200)
    h4['risk_on'] = (h4['close'] > h4['ema200']) & (h4['ema20'] > h4['ema50'])
    return h4[['risk_on']].shift(1)['risk_on'].reindex(d.index, method='ffill').fillna(False)


def make_entries(data, daily_universe, btc_filter):
    entries = []
    for m, d in data.items():
        idxs = np.flatnonzero((d['breakout'] & d['trend_ok']).fillna(False).values)
        for i in idxs:
            if i + 2 >= len(d):
                continue
            level = float(d.iloc[i]['prior20_high'])
            # Retest must happen quickly, reducing stale breakouts.
            for j in range(i + 1, min(i + 5, len(d) - 1)):
                r = d.iloc[j]
                touched = r['low'] <= level * 1.002
                held = r['close'] >= level and bool(r['green'])
                not_overheated = float(r['mom_1h']) < 0.06
                if touched and held and not_overheated:
                    nxt = d.iloc[j + 1]
                    day = nxt.name.floor('D')
                    if m not in daily_universe.get(day, set()):
                        break
                    if nxt.name not in btc_filter.index or not bool(btc_filter.loc[nxt.name]):
                        break
                    entry = float(nxt['open']) * (1 + SLIPPAGE)
                    stop = min(float(r['low']) * 0.998, entry - 1.5 * float(r['atr14']))
                    risk_pct = (entry - stop) / entry
                    if risk_pct < 0.005 or risk_pct > 0.04:
                        break
                    score = (
                        float(d.iloc[i]['value_ratio']) * 2.0 +
                        float(d.iloc[i]['flow_accel']) +
                        max(0.0, float(d.iloc[i]['mom_1h']) * 30.0)
                    )
                    entries.append({'time':nxt.name,'market':m,'score':score,'stop':stop})
                    break
    if not entries:
        return pd.DataFrame()
    return pd.DataFrame(entries).sort_values(['time','score'], ascending=[True,False])


def run_variant(data, entries, mode):
    grouped = {t:g for t,g in entries.groupby('time')}
    timeline = sorted(set().union(*[set(d.index) for d in data.values()]))
    capital = START_CAPITAL
    peak = capital
    max_dd = 0.0
    position = None
    trades = []
    eq_rows = []
    last_entry_day = None

    for t in timeline:
        if position is not None:
            m = position['market']
            d = data[m]
            if t in d.index:
                bar = d.loc[t]
                exit_price = None
                reason = None
                if bar['low'] <= position['stop']:
                    exit_price = position['stop'] * (1 - SLIPPAGE)
                    reason = 'stop'
                else:
                    r = position['risk']
                    if mode == '1.5R':
                        target = position['entry'] + 1.5*r
                    elif mode == '2R':
                        target = position['entry'] + 2.0*r
                    elif mode == '3R':
                        target = position['entry'] + 3.0*r
                    else:
                        target = position['entry'] + 2.0*r

                    if mode != 'TRAIL':
                        if bar['high'] >= target:
                            exit_price = target * (1 - SLIPPAGE)
                            reason = mode
                    else:
                        if not position['armed'] and bar['high'] >= target:
                            position['armed'] = True
                            position['stop'] = max(position['stop'], position['entry'])
                        if position['armed'] and bar['close'] < bar['ema20']:
                            exit_price = float(bar['close']) * (1 - SLIPPAGE)
                            reason = 'ema20_trail'

                if exit_price is not None:
                    capital = position['qty'] * exit_price * (1 - FEE)
                    ret = capital / position['capital_before'] - 1
                    trades.append({'market':m,'entry_time':position['time'],'exit_time':t,
                                   'return_pct':ret*100,'reason':reason})
                    position = None

        # Max one new position per UTC day.
        day = t.floor('D')
        if position is None and t in grouped and day != last_entry_day:
            for _, sig in grouped[t].iterrows():
                m = sig['market']
                if m not in data or t not in data[m].index:
                    continue
                entry = float(data[m].loc[t,'open']) * (1 + SLIPPAGE)
                stop = float(sig['stop'])
                risk = entry - stop
                if risk <= 0:
                    continue
                # One coin at a time, but cap capital at risk so stop-loss ~= 2% account risk.
                risk_cash = capital * 0.02
                qty_by_risk = risk_cash / risk
                qty_by_cash = (capital * (1 - FEE)) / entry
                qty = min(qty_by_risk, qty_by_cash)
                if qty <= 0:
                    continue
                cash_used = qty * entry / (1 - FEE)
                reserve = max(0.0, capital - cash_used)
                before = capital
                position = {'market':m,'time':t,'entry':entry,'stop':stop,'risk':risk,'qty':qty,
                            'reserve':reserve,'capital_before':before,'armed':False}
                capital = reserve
                last_entry_day = day
                break

        eq = capital
        if position is not None:
            m = position['market']
            if t in data[m].index:
                eq += position['qty'] * float(data[m].loc[t,'close']) * (1 - FEE)
        peak = max(peak, eq)
        dd = (peak - eq) / peak if peak else 0
        max_dd = max(max_dd, dd)
        eq_rows.append((t, eq))

    if position is not None:
        m = position['market']
        last = data[m].iloc[-1]
        capital += position['qty'] * float(last['close']) * (1 - SLIPPAGE) * (1 - FEE)
        ret = capital / position['capital_before'] - 1
        trades.append({'market':m,'entry_time':position['time'],'exit_time':data[m].index[-1],
                       'return_pct':ret*100,'reason':'end'})

    tr = pd.DataFrame(trades)
    if len(tr):
        wins = tr[tr['return_pct'] > 0]
        losses = tr[tr['return_pct'] <= 0]
        gw = wins['return_pct'].sum()
        gl = -losses['return_pct'].sum()
        pf = gw/gl if gl > 0 else math.inf
        wr = len(wins)/len(tr)*100
    else:
        pf = 0.0; wr = 0.0
    return {
        'mode':mode,'final':capital,'return_pct':(capital/START_CAPITAL-1)*100,
        'trades':len(tr),'win_rate_pct':wr,'profit_factor':pf,'mdd_pct':max_dd*100,
        'trades_df':tr,'equity':pd.DataFrame(eq_rows, columns=['time','equity'])
    }


def main():
    end = datetime.now(timezone.utc).replace(second=0, microsecond=0)
    start = end - timedelta(days=DAYS)
    warmup = start - timedelta(days=40)

    markets = get_json('/market/all', {'is_details':'false'})
    krw = sorted([x['market'] for x in markets if x['market'].startswith('KRW-')])
    print('KRW markets:', len(krw))

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
        vals.sort(key=lambda x:x[1], reverse=True)
        picks = [m for m,_ in vals[:TOP_DAILY]]
        daily_universe[day] = set(picks)
        for m in picks:
            freq[m] = freq.get(m,0) + 1

    candidates = [m for m,_ in sorted(freq.items(), key=lambda kv:kv[1], reverse=True)[:MAX_CANDIDATES]]
    if 'KRW-BTC' not in candidates:
        candidates.append('KRW-BTC')
    print('Candidates:', candidates)

    data = {}
    for idx,m in enumerate(candidates,1):
        try:
            df = fetch_candles(m,15,warmup,end)
            if len(df) > 1000:
                data[m] = build_features(df)
                print('15m',idx,'/',len(candidates),m,len(df))
        except Exception as e:
            print('15m skip',m,e)

    if 'KRW-BTC' not in data:
        raise RuntimeError('BTC data unavailable')
    btc_filter = build_btc_filter(data['KRW-BTC'][['open','high','low','close','volume','value']])
    entries = make_entries(data,daily_universe,btc_filter)
    print('Strict entries:', len(entries))
    if entries.empty:
        raise RuntimeError('No entries generated')

    variants = [run_variant(data,entries,x) for x in ['1.5R','2R','3R','TRAIL']]
    rows = []
    for v in variants:
        rows.append({
            'strategy':'Upbit MoneyFlow v2','exit_mode':v['mode'],
            'start_capital_krw':START_CAPITAL,'final_capital_krw':round(v['final'],2),
            'return_pct':round(v['return_pct'],4),'trades':v['trades'],
            'win_rate_pct':round(v['win_rate_pct'],4),
            'profit_factor':round(v['profit_factor'],4) if np.isfinite(v['profit_factor']) else 'inf',
            'max_drawdown_pct':round(v['mdd_pct'],4),
            'daily_top_n':TOP_DAILY,'risk_per_trade_pct':2.0,
            'fee_each_fill_pct':FEE*100,'slippage_each_fill_pct':SLIPPAGE*100
        })
    res = pd.DataFrame(rows).sort_values('final_capital_krw', ascending=False)
    res.to_csv('backtest_results.csv', index=False)
    best_mode = res.iloc[0]['exit_mode']
    best = next(v for v in variants if v['mode'] == best_mode)
    best['trades_df'].to_csv('upbit_moneyflow_v2_trades.csv', index=False)
    ec = best['equity'].drop_duplicates('time').set_index('time')
    plt.figure(figsize=(12,5))
    plt.plot(ec.index,ec['equity'])
    plt.title(f'Upbit MoneyFlow v2 - Best exit {best_mode}')
    plt.ylabel('KRW'); plt.xlabel('Time'); plt.tight_layout()
    plt.savefig('backtest_equity.png', dpi=150)
    print(res.to_string(index=False))


if __name__ == '__main__':
    main()
