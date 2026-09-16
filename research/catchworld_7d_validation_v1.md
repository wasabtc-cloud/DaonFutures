# Catch World 7-day validation V1

Paper validation only. No automatic orders.

Duration: 7 days from the first eligible live signal.

Compare the same eligible events with three methods:
- A: Flow + pullback
- B: A + executed trade pressure
- C: B + order-book behavior

Primary pullback research zone: -2.0% to -2.5% after a Flow surge.

Track every eligible event, including rejected entries. Save event time, market, Flow, pullback, entry/exit price and time, buy/sell executed value, buy/sell ratio, bid/ask depth, imbalance, spread, market-flow context, reject reason, and 30m/1h/2h/6h MFE and MAE.

State path: DETECT -> WAIT_PULLBACK -> WATCH -> BUY -> HOLD -> SELL.

Also compare full exit at +3% with 50% exit at +3% and adaptive exit for the remainder.

After 7 days compare trade count, win rate, profit factor, net return, drawdown, MFE/MAE, entry delay, continued-decline rate, missed-rebound rate and coin concentration.

Do not change thresholds after the first eligible live signal. A material rule change creates a new version and a new forward window.

For final PnL, verify the applicable Upbit KRW trading fee and apply buy and sell fees separately. Any slippage assumption is reported separately, not mixed into the exchange fee.
