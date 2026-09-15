package com.daon.futures

import kotlin.math.pow
import kotlin.math.sqrt

object CatchWorldIndicators {
    fun snapshot(market: String, candles: List<UpbitCandle>, priorWhaleSeen: Boolean = false): CatchWorldSnapshot? {
        if (candles.size < 80) return null
        val closes = candles.map { it.close }
        val ema20 = ema(closes, 20)
        val ema60 = ema(closes, 60)
        val rsi = rsi(closes, 14)
        val bb = bbWidth(closes, 20)
        val oneHourBars = 4
        val v1h = candles.takeLast(oneHourBars).sumOf { it.tradePrice }
        val history = candles.dropLast(oneHourBars)
        val hourly = history.chunked(oneHourBars).map { b -> b.sumOf { it.tradePrice } }.takeLast(120)
        val base = hourly.sorted().let { if (it.isEmpty()) 0.0 else it[it.size / 2] }
        val vr = if (base > 0) v1h / base else 0.0
        val ret1h = closes.last() / closes[closes.size - 1 - oneHourBars] - 1.0
        return CatchWorldSnapshot(
            market = market,
            price = closes.last(),
            ema20 = ema20,
            ema60 = ema60,
            rsi14 = rsi,
            bbWidth = bb,
            volumeRatio1h = vr,
            return1h = ret1h,
            priorWhaleSeen = priorWhaleSeen
        )
    }

    private fun ema(x: List<Double>, n: Int): Double {
        val k = 2.0 / (n + 1.0)
        var e = x.take(n).average()
        for (v in x.drop(n)) e = v * k + e * (1.0 - k)
        return e
    }

    private fun rsi(x: List<Double>, n: Int): Double {
        val d = x.zipWithNext { a, b -> b - a }.takeLast(n)
        val gain = d.filter { it > 0 }.sum() / n
        val loss = -d.filter { it < 0 }.sum() / n
        if (loss == 0.0) return 100.0
        val rs = gain / loss
        return 100.0 - 100.0 / (1.0 + rs)
    }

    private fun bbWidth(x: List<Double>, n: Int): Double {
        val w = x.takeLast(n)
        val mean = w.average()
        if (mean == 0.0) return 0.0
        val sd = sqrt(w.sumOf { (it - mean).pow(2) } / w.size)
        return (4.0 * sd) / mean
    }
}
