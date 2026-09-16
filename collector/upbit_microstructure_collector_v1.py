"""CatchWorld Upbit Microstructure Collector V1.

Collects synchronized KRW-market trade and orderbook streams for later research.
This is a data collector/sensor, NOT a BUY/SELL strategy.

Outputs JSONL partitions containing:
- raw trades: price, volume, notional, ask/bid side
- raw orderbook top levels and totals
- rolling 1m/5m/15m trade summaries incl. signed delta/CVD proxy
- repeated similar-notional trade sensor

Run on a persistent machine/server; GitHub Actions is not intended for continuous collection.
"""
from __future__ import annotations

import asyncio
import json
import math
import os
import time
from collections import defaultdict, deque
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import aiohttp

WS_URL = "wss://api.upbit.com/websocket/v1"
REST_MARKETS = "https://api.upbit.com/v1/market/all"
OUT = Path(os.getenv("CW_MICRO_OUT", "data/microstructure"))
OUT.mkdir(parents=True, exist_ok=True)

# Keep enough recent trades to compute sensors without unbounded memory.
recent = defaultdict(lambda: deque(maxlen=20000))
cvd = defaultdict(float)


def utc_hour() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%d_%H")


def append(kind: str, row: dict[str, Any]) -> None:
    d = OUT / kind
    d.mkdir(parents=True, exist_ok=True)
    with (d / f"{utc_hour()}.jsonl").open("a", encoding="utf-8") as f:
        f.write(json.dumps(row, ensure_ascii=False, separators=(",", ":")) + "\n")


async def krw_markets(session: aiohttp.ClientSession) -> list[str]:
    async with session.get(REST_MARKETS, params={"isDetails": "false"}, timeout=20) as r:
        r.raise_for_status()
        data = await r.json()
    return sorted(x["market"] for x in data if x["market"].startswith("KRW-"))


def trade_row(m: dict[str, Any]) -> dict[str, Any]:
    price = float(m["trade_price"])
    vol = float(m["trade_volume"])
    side = str(m.get("ask_bid", ""))
    signed = price * vol * (1.0 if side == "BID" else -1.0)
    market = m["code"]
    cvd[market] += signed
    return {
        "recv_ms": int(time.time() * 1000), "market": market,
        "trade_ts_ms": m.get("trade_timestamp"), "sequential_id": m.get("sequential_id"),
        "price": price, "volume": vol, "notional": price * vol,
        "side": side, "signed_notional": signed, "cvd_notional": cvd[market],
    }


def repeat_sensor(market: str, now_ms: int) -> dict[str, Any] | None:
    """Detect repeated similar-sized prints. Descriptive only; not proof of a bot/accumulation."""
    q = recent[market]
    cutoff = now_ms - 60_000
    xs = [x for x in q if x["trade_ts_ms"] and x["trade_ts_ms"] >= cutoff]
    if len(xs) < 8:
        return None
    # Bucket by ~2% notional width in log space, allowing any amount band (not hard-coded 5,000 KRW).
    buckets: dict[tuple[int, str], list[dict[str, Any]]] = defaultdict(list)
    for x in xs:
        n = max(float(x["notional"]), 1.0)
        bucket = int(round(math.log(n) / math.log(1.02)))
        buckets[(bucket, x["side"])].append(x)
    key, grp = max(buckets.items(), key=lambda kv: len(kv[1]))
    if len(grp) < 6:
        return None
    notionals = sorted(x["notional"] for x in grp)
    return {
        "ts_ms": now_ms, "market": market, "side": key[1], "count_60s": len(grp),
        "median_notional": notionals[len(notionals)//2],
        "sum_notional": sum(x["notional"] for x in grp),
        "first_price": grp[0]["price"], "last_price": grp[-1]["price"],
        "price_response": grp[-1]["price"] / grp[0]["price"] - 1.0 if grp[0]["price"] else None,
    }


def orderbook_row(m: dict[str, Any]) -> dict[str, Any]:
    units = m.get("orderbook_units", [])
    return {
        "recv_ms": int(time.time() * 1000), "market": m["code"], "timestamp": m.get("timestamp"),
        "total_ask_size": m.get("total_ask_size"), "total_bid_size": m.get("total_bid_size"),
        "levels": [{"ask_price": u.get("ask_price"), "bid_price": u.get("bid_price"),
                    "ask_size": u.get("ask_size"), "bid_size": u.get("bid_size")} for u in units[:15]],
    }


async def consume(markets: list[str]) -> None:
    # Chunk connections to avoid oversized subscriptions and make reconnects manageable.
    chunks = [markets[i:i+80] for i in range(0, len(markets), 80)]

    async def worker(codes: list[str], idx: int) -> None:
        while True:
            try:
                async with aiohttp.ClientSession() as session:
                    async with session.ws_connect(WS_URL, heartbeat=30, receive_timeout=90) as ws:
                        sub = [
                            {"ticket": f"catchworld-micro-v1-{idx}"},
                            {"type": "trade", "codes": codes, "is_only_realtime": True},
                            {"type": "orderbook", "codes": codes, "is_only_realtime": True},
                            {"format": "DEFAULT"},
                        ]
                        await ws.send_str(json.dumps(sub))
                        async for msg in ws:
                            if msg.type == aiohttp.WSMsgType.BINARY:
                                m = json.loads(msg.data.decode("utf-8"))
                            elif msg.type == aiohttp.WSMsgType.TEXT:
                                m = json.loads(msg.data)
                            else:
                                continue
                            typ = m.get("type")
                            if typ == "trade":
                                row = trade_row(m)
                                recent[row["market"]].append(row)
                                append("trades", row)
                                s = repeat_sensor(row["market"], int(row["recv_ms"]))
                                if s:
                                    append("repeat_sensor", s)
                            elif typ == "orderbook":
                                append("orderbook", orderbook_row(m))
            except Exception as e:
                append("system", {"ts_ms": int(time.time()*1000), "worker": idx, "error": repr(e)})
                await asyncio.sleep(5)

    await asyncio.gather(*(worker(c, i) for i, c in enumerate(chunks)))


async def main() -> None:
    async with aiohttp.ClientSession() as session:
        markets = await krw_markets(session)
    append("system", {"ts_ms": int(time.time()*1000), "event": "start", "markets": len(markets)})
    await consume(markets)


if __name__ == "__main__":
    asyncio.run(main())
