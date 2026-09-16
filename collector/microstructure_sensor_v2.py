"""CatchWorld Microstructure Sensor V2.

Research-only causal sensors computed from synchronized trade/orderbook streams.
No BUY/SELL decisions. Outputs interpretable measurements for later event-study validation:
- rolling Delta/CVD
- downside/upside absorption candidates
- bid/ask refill candidates
- repeated similar-notional trade activity

Input dictionaries follow upbit_microstructure_collector_v1.py fields.
"""
from __future__ import annotations
from collections import defaultdict, deque
from dataclasses import dataclass
from statistics import median
from typing import Any

WINDOWS_MS = {"1m": 60_000, "5m": 300_000, "15m": 900_000}

@dataclass
class BookPoint:
    ts: int
    best_bid: float
    best_ask: float
    bid_size: float
    ask_size: float
    total_bid: float
    total_ask: float

class MicrostructureSensorV2:
    def __init__(self) -> None:
        self.trades = defaultdict(lambda: deque(maxlen=50_000))
        self.books = defaultdict(lambda: deque(maxlen=10_000))

    def on_trade(self, t: dict[str, Any]) -> dict[str, Any]:
        market = t["market"]
        self.trades[market].append(t)
        ts = int(t.get("trade_ts_ms") or t["recv_ms"])
        out = {"market": market, "ts_ms": ts, "type": "micro_v2"}
        for name, ms in WINDOWS_MS.items():
            xs = self._trades_since(market, ts-ms)
            buy = sum(float(x["notional"]) for x in xs if x["side"] == "BID")
            sell = sum(float(x["notional"]) for x in xs if x["side"] == "ASK")
            total = buy + sell
            out[f"buy_{name}"] = buy
            out[f"sell_{name}"] = sell
            out[f"delta_{name}"] = buy-sell
            out[f"delta_ratio_{name}"] = (buy-sell)/total if total else 0.0
            if xs:
                p0, p1 = float(xs[0]["price"]), float(xs[-1]["price"])
                out[f"ret_{name}"] = p1/p0-1 if p0 else 0.0
        out.update(self._repeat_features(market, ts))
        out.update(self._absorption_features(market, ts))
        return out

    def on_orderbook(self, b: dict[str, Any]) -> dict[str, Any]:
        market = b["market"]
        levels = b.get("levels") or []
        if not levels:
            return {"market": market, "type": "book_v2", "valid": False}
        u = levels[0]
        p = BookPoint(
            ts=int(b.get("timestamp") or b["recv_ms"]),
            best_bid=float(u["bid_price"]), best_ask=float(u["ask_price"]),
            bid_size=float(u["bid_size"]), ask_size=float(u["ask_size"]),
            total_bid=float(b.get("total_bid_size") or 0), total_ask=float(b.get("total_ask_size") or 0),
        )
        self.books[market].append(p)
        return self._refill_features(market, p.ts)

    def _trades_since(self, market: str, cutoff: int):
        return [x for x in self.trades[market] if int(x.get("trade_ts_ms") or x["recv_ms"]) >= cutoff]

    def _repeat_features(self, market: str, ts: int) -> dict[str, Any]:
        xs = self._trades_since(market, ts-60_000)
        if len(xs) < 6:
            return {"repeat_count_60s": 0, "repeat_side": None, "repeat_notional_med": None}
        # Adaptive ~5% bands around observed notionals; no fixed 5,000-KRW assumption.
        best = []
        for x in xs:
            n = float(x["notional"])
            if n <= 0: continue
            grp = [y for y in xs if y["side"] == x["side"] and abs(float(y["notional"])/n-1) <= .05]
            if len(grp) > len(best): best = grp
        if len(best) < 6:
            return {"repeat_count_60s": 0, "repeat_side": None, "repeat_notional_med": None}
        return {"repeat_count_60s": len(best), "repeat_side": best[0]["side"],
                "repeat_notional_med": median(float(x["notional"]) for x in best),
                "repeat_notional_sum": sum(float(x["notional"]) for x in best)}

    def _absorption_features(self, market: str, ts: int) -> dict[str, Any]:
        xs = self._trades_since(market, ts-60_000)
        if len(xs) < 4:
            return {"down_absorption": False, "up_absorption": False}
        buy = sum(float(x["notional"]) for x in xs if x["side"] == "BID")
        sell = sum(float(x["notional"]) for x in xs if x["side"] == "ASK")
        p0, p1 = float(xs[0]["price"]), float(xs[-1]["price"])
        ret = p1/p0-1 if p0 else 0.0
        total = buy+sell
        imbalance = (buy-sell)/total if total else 0.0
        # Candidate labels only. Thresholds are deliberately simple and must be validated,
        # not treated as trading rules.
        return {
            "trade_imbalance_1m": imbalance,
            "price_response_1m": ret,
            "down_absorption": imbalance <= -.25 and ret > -.0025,
            "up_absorption": imbalance >= .25 and ret < .0025,
        }

    def _refill_features(self, market: str, ts: int) -> dict[str, Any]:
        xs = [x for x in self.books[market] if x.ts >= ts-60_000]
        if len(xs) < 3:
            return {"market": market, "ts_ms": ts, "type": "book_v2", "valid": True,
                    "bid_refill": False, "ask_refill": False}
        bid_sizes = [x.bid_size for x in xs]
        ask_sizes = [x.ask_size for x in xs]
        bid_min_i = min(range(len(xs)), key=lambda i: bid_sizes[i])
        ask_min_i = min(range(len(xs)), key=lambda i: ask_sizes[i])
        bid_min = bid_sizes[bid_min_i]; ask_min = ask_sizes[ask_min_i]
        # Refill means size was depleted and subsequently rebuilt at/near the best level.
        bid_refill_ratio = xs[-1].bid_size / bid_min if bid_min > 0 and bid_min_i < len(xs)-1 else 1.0
        ask_refill_ratio = xs[-1].ask_size / ask_min if ask_min > 0 and ask_min_i < len(xs)-1 else 1.0
        spread = xs[-1].best_ask/xs[-1].best_bid-1 if xs[-1].best_bid else None
        return {"market": market, "ts_ms": ts, "type": "book_v2", "valid": True,
                "best_bid": xs[-1].best_bid, "best_ask": xs[-1].best_ask, "spread": spread,
                "bid_refill_ratio_60s": bid_refill_ratio, "ask_refill_ratio_60s": ask_refill_ratio,
                "bid_refill": bid_refill_ratio >= 1.5,
                "ask_refill": ask_refill_ratio >= 1.5,
                "book_imbalance": (xs[-1].total_bid-xs[-1].total_ask)/(xs[-1].total_bid+xs[-1].total_ask)
                    if xs[-1].total_bid+xs[-1].total_ask else 0.0}
