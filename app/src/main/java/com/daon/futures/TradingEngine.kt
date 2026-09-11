package com.daon.futures

object TradingEngine {
    fun ema(values: List<Double>, period: Int): Double {
        if (values.isEmpty()) return 0.0
        val seed = values.take(minOf(period, values.size)).average()
        val k = 2.0 / (period + 1)
        var e = seed
        for (i in minOf(period, values.size) until values.size) {
            e = values[i] * k + e * (1 - k)
        }
        return e
    }

    fun rsi(values: List<Double>, period: Int = 14): Double {
        if (values.size <= period) return 50.0
        var gain = 0.0
        var loss = 0.0
        for (i in 1..period) {
            val d = values[i] - values[i - 1]
            if (d >= 0) gain += d else loss -= d
        }
        gain /= period
        loss /= period
        for (i in period + 1 until values.size) {
            val d = values[i] - values[i - 1]
            gain = (gain * (period - 1) + if (d > 0) d else 0.0) / period
            loss = (loss * (period - 1) + if (d < 0) -d else 0.0) / period
        }
        return if (loss == 0.0) 100.0 else 100.0 - (100.0 / (1.0 + gain / loss))
    }

    /**
     * DaonFutures One Candle Rule
     *
     * 1) 4H + 1H EMA20/EMA50로 방향을 제한한다.
     * 2) 상승 추세: 최근 20개 15분봉 중 가장 높은 위치의 음봉을 지지 기준 캔들로 잡는다.
     *    하락 추세: 가장 낮은 위치의 양봉을 저항 기준 캔들로 잡는다.
     * 3) 가격이 기준 캔들 몸통을 리테스트한 뒤 추세 방향으로 마감하면 진입한다.
     * 4) 기본 손절은 기준 캔들 몸통 반대편 이탈, 목표는 최소 2R이다.
     *
     * slPct는 기준 캔들 손절값이 비정상적일 때만 안전한 fallback으로 사용한다.
     * tpPct는 기존 API 호환을 위해 유지하지만 One Candle Rule의 기본 목표는 2R이다.
     */
    fun signal(
        c15: List<Candle>,
        c1h: List<Candle>,
        c4h: List<Candle>,
        slPct: Double,
        tpPct: Double
    ): Signal? = oneCandleSignal(c15, c1h, c4h, slPct)

    fun oneCandleSignal(
        c15: List<Candle>,
        c1h: List<Candle>,
        c4h: List<Candle>,
        fallbackSlPct: Double = 1.0,
        lookback: Int = 20,
        rMultiple: Double = 2.0
    ): Signal? {
        if (c15.size < 55 || c1h.size < 55 || c4h.size < 55) return null

        val p15 = c15.map { it.close }
        val p1 = c1h.map { it.close }
        val p4 = c4h.map { it.close }
        val r = rsi(p15)

        val upTrend = ema(p4, 20) > ema(p4, 50) && ema(p1, 20) > ema(p1, 50)
        val downTrend = ema(p4, 20) < ema(p4, 50) && ema(p1, 20) < ema(p1, 50)
        if (!upTrend && !downTrend) return null

        val last = c15.last()
        val prev = c15[c15.size - 2]
        val start = maxOf(0, c15.size - lookback - 2)
        val candidates = c15.subList(start, c15.size - 2)

        if (upTrend) {
            val key = candidates.filter { it.close < it.open }.maxByOrNull { it.high } ?: return null
            val bodyLow = minOf(key.open, key.close)
            val bodyHigh = maxOf(key.open, key.close)
            val retested = overlaps(prev, bodyLow, bodyHigh) || overlaps(last, bodyLow, bodyHigh)
            val confirmed = last.close >= bodyHigh && last.close > last.open
            if (!retested || !confirmed) return null

            val entry = last.close
            var stop = bodyLow
            if (stop <= 0.0 || stop >= entry) stop = entry * (1 - fallbackSlPct / 100.0)
            val risk = entry - stop
            if (risk <= 0.0) return null
            val target = entry + risk * rMultiple
            return Signal(
                side = "LONG",
                price = entry,
                sl = stop,
                tp = target,
                rsi = r,
                reason = "One Candle Rule · 4H/1H 상승 · 최고 위치 음봉 리테스트 지지 · 2R 목표",
                candleTime = last.closeTime
            )
        }

        val key = candidates.filter { it.close > it.open }.minByOrNull { it.low } ?: return null
        val bodyLow = minOf(key.open, key.close)
        val bodyHigh = maxOf(key.open, key.close)
        val retested = overlaps(prev, bodyLow, bodyHigh) || overlaps(last, bodyLow, bodyHigh)
        val confirmed = last.close <= bodyLow && last.close < last.open
        if (!retested || !confirmed) return null

        val entry = last.close
        var stop = bodyHigh
        if (stop <= entry) stop = entry * (1 + fallbackSlPct / 100.0)
        val risk = stop - entry
        if (risk <= 0.0) return null
        val target = entry - risk * rMultiple
        return Signal(
            side = "SHORT",
            price = entry,
            sl = stop,
            tp = target,
            rsi = r,
            reason = "One Candle Rule · 4H/1H 하락 · 최저 위치 양봉 리테스트 저항 · 2R 목표",
            candleTime = last.closeTime
        )
    }

    private fun overlaps(c: Candle, zoneLow: Double, zoneHigh: Double): Boolean =
        c.low <= zoneHigh && c.high >= zoneLow
}
