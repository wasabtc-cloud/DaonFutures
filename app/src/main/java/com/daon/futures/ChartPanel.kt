package com.daon.futures

import androidx.compose.foundation.Canvas
import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.Card
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.ui.Modifier
import androidx.compose.ui.geometry.Offset
import androidx.compose.ui.geometry.Size
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.Path
import androidx.compose.ui.graphics.drawscope.Stroke
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import java.util.Locale
import kotlin.math.abs
import kotlin.math.max
import kotlin.math.min

fun emaSeries(values: List<Double>, period: Int): List<Double> {
    if (values.isEmpty()) return emptyList()
    val k = 2.0 / (period + 1.0)
    val out = MutableList(values.size) { 0.0 }
    var ema = values.first()
    out[0] = ema
    for (i in 1 until values.size) {
        ema = values[i] * k + ema * (1.0 - k)
        out[i] = ema
    }
    return out
}

fun rsiValue(values: List<Double>, period: Int = 14): Double {
    if (values.size <= period) return 50.0
    var gains = 0.0
    var losses = 0.0
    for (i in values.size - period until values.size) {
        val d = values[i] - values[i - 1]
        if (d >= 0.0) gains += d else losses -= d
    }
    if (losses == 0.0) return 100.0
    val rs = (gains / period) / (losses / period)
    return 100.0 - 100.0 / (1.0 + rs)
}

private data class OneCandleZone(
    val index: Int,
    val low: Double,
    val high: Double,
    val side: String,
    val retested: Boolean,
    val confirmed: Boolean,
    val entry: Double?,
    val stop: Double?,
    val target2R: Double?
)

private fun oneCandleZone(
    candles: List<Candle>,
    e20: List<Double>,
    e50: List<Double>
): OneCandleZone? {
    if (candles.size < 22 || e20.isEmpty() || e50.isEmpty()) return null

    val bullish = e20.last() > e50.last()
    val start = maxOf(0, candles.size - 21)
    val end = candles.size - 1
    val indexed = (start until end).map { it to candles[it] }

    val key = (if (bullish) {
        indexed
            .filter { (_, c) -> c.close < c.open }
            .maxByOrNull { (_, c) -> c.high }
    } else {
        indexed
            .filter { (_, c) -> c.close > c.open }
            .minByOrNull { (_, c) -> c.low }
    }) ?: return null

    val (idx, candle) = key
    val low = minOf(candle.open, candle.close)
    val high = maxOf(candle.open, candle.close)
    val after = candles.drop(idx + 1)
    val retested = after.any { c -> c.low <= high && c.high >= low }
    val last = candles.last()
    val confirmed = retested && if (bullish) last.close > high else last.close < low
    val side = if (bullish) "LONG" else "SHORT"

    if (!confirmed) {
        return OneCandleZone(idx, low, high, side, retested, false, null, null, null)
    }

    val entry = last.close
    val stop = if (bullish) low else high
    val risk = if (bullish) entry - stop else stop - entry

    if (risk <= 0.0) {
        return OneCandleZone(idx, low, high, side, retested, false, null, null, null)
    }

    val target = if (bullish) entry + risk * 2.0 else entry - risk * 2.0
    return OneCandleZone(idx, low, high, side, true, true, entry, stop, target)
}

@Composable
fun MarketChartCard(
    symbol: String,
    intervalLabel: String,
    candles: List<Candle>,
    modifier: Modifier = Modifier
) {
    val visible = if (candles.size > 60) candles.takeLast(60) else candles
    val closes = visible.map { it.close }
    val e20 = emaSeries(closes, 20)
    val e50 = emaSeries(closes, 50)
    val rsi = rsiValue(closes)
    val zone = oneCandleZone(visible, e20, e50)

    Card(modifier = modifier.fillMaxWidth(), shape = RoundedCornerShape(18.dp)) {
        Column(
            Modifier.padding(14.dp),
            verticalArrangement = Arrangement.spacedBy(8.dp)
        ) {
            Text("$symbol · $intervalLabel · BINANCE", fontWeight = FontWeight.Bold, fontSize = 18.sp)

            if (visible.size < 2) {
                Text("차트 데이터를 불러오는 중입니다.", color = Color.Gray)
            } else {
                Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.SpaceBetween) {
                    Text("EMA20 ${fmtChart(e20.lastOrNull())}", color = Color(0xFF35A7FF), fontSize = 13.sp)
                    Text("EMA50 ${fmtChart(e50.lastOrNull())}", color = Color(0xFFFFA000), fontSize = 13.sp)
                    Text("RSI ${String.format(Locale.KOREA, "%.1f", rsi)}", color = Color(0xFFA875FF), fontSize = 13.sp)
                }

                zone?.let {
                    val col = if (it.side == "LONG") Color(0xFF21D58B) else Color(0xFFFF4058)
                    val state = when {
                        it.confirmed -> "진입 확정"
                        it.retested -> "리테스트 확인 · 방향 확인 대기"
                        else -> "리테스트 대기"
                    }
                    Text(
                        "One Candle ${it.side} · 기준 ${fmtChart(it.low)} ~ ${fmtChart(it.high)} · $state",
                        color = col,
                        fontWeight = FontWeight.Bold,
                        fontSize = 12.sp
                    )
                } ?: Text("One Candle · 기준 캔들 탐색 중", color = Color.Gray, fontSize = 12.sp)

                CandlestickCanvas(visible, e20, e50, zone)

                zone?.takeIf { it.confirmed }?.let {
                    Text(
                        "진입 ${fmtChart(it.entry)} · SL ${fmtChart(it.stop)} · 2R ${fmtChart(it.target2R)}",
                        color = if (it.side == "LONG") Color(0xFF21D58B) else Color(0xFFFF4058),
                        fontWeight = FontWeight.Bold,
                        fontSize = 12.sp
                    )
                }

                Text("RSI 14  ${String.format(Locale.KOREA, "%.2f", rsi)}", color = Color(0xFFA875FF), fontSize = 13.sp)
                RsiCanvas(closes)
            }
        }
    }
}

@Composable
private fun CandlestickCanvas(
    candles: List<Candle>,
    e20: List<Double>,
    e50: List<Double>,
    zone: OneCandleZone?
) {
    val up = Color(0xFF18C98B)
    val down = Color(0xFFFF4058)
    val blue = Color(0xFF2196F3)
    val orange = Color(0xFFFFA000)
    val grid = Color(0xFF29313D)

    Canvas(
        Modifier
            .fillMaxWidth()
            .height(360.dp)
            .background(Color(0xFF090E16), RoundedCornerShape(12.dp))
    ) {
        val extras = mutableListOf<Double>()
        zone?.let {
            extras += it.low
            extras += it.high
            it.stop?.let { v -> extras += v }
            it.target2R?.let { v -> extras += v }
        }

        val candleMax = candles.maxOf { it.high }
        val candleMin = candles.minOf { it.low }
        val maxP = max(candleMax, extras.maxOrNull() ?: candleMax)
        val minP = min(candleMin, extras.minOrNull() ?: candleMin)
        val rawRange = maxP - minP
        val range = if (rawRange <= 0.0) 1.0 else rawRange
        val pad = range * 0.12
        val top = maxP + pad
        val bottom = minP - pad
        val full = top - bottom

        fun y(v: Double): Float = ((top - v) / full * size.height).toFloat()

        val plotWidth = size.width * 0.88f
        for (g in 1..5) {
            val gy = size.height * g / 6f
            drawLine(grid, Offset(0f, gy), Offset(plotWidth, gy), 1f)
        }

        val step = plotWidth / candles.size
        val body = max(2f, step * 0.58f)

        zone?.let {
            val zoneColor = if (it.side == "LONG") up else down
            val left = (step * it.index).coerceAtLeast(0f)
            val topY = min(y(it.high), y(it.low))
            val bottomY = max(y(it.high), y(it.low))
            drawRect(
                color = zoneColor.copy(alpha = 0.20f),
                topLeft = Offset(left, topY),
                size = Size(plotWidth - left, max(3f, bottomY - topY))
            )
            drawLine(zoneColor, Offset(left, topY), Offset(plotWidth, topY), 2f)
            drawLine(zoneColor, Offset(left, bottomY), Offset(plotWidth, bottomY), 2f)
        }

        candles.forEachIndexed { i, candle ->
            val x = step * i + step / 2f
            val candleColor = if (candle.close >= candle.open) up else down
            val openY = y(candle.open)
            val closeY = y(candle.close)
            drawLine(candleColor, Offset(x, y(candle.high)), Offset(x, y(candle.low)), 1.4f)
            drawRect(
                color = candleColor,
                topLeft = Offset(x - body / 2f, min(openY, closeY)),
                size = Size(body, max(2f, abs(closeY - openY)))
            )
        }

        fun drawEma(series: List<Double>, color: Color) {
            if (series.size < 2) return
            val path = Path()
            series.forEachIndexed { i, value ->
                val point = Offset(step * i + step / 2f, y(value))
                if (i == 0) path.moveTo(point.x, point.y) else path.lineTo(point.x, point.y)
            }
            drawPath(path, color, style = Stroke(width = 2.5f))
        }

        drawEma(e20, blue)
        drawEma(e50, orange)

        zone?.takeIf { it.confirmed }?.let { z ->
            val entry = z.entry
            val stop = z.stop
            val target = z.target2R
            if (entry != null && stop != null && target != null) {
                val signalColor = if (z.side == "LONG") up else down
                drawLine(signalColor, Offset(0f, y(entry)), Offset(plotWidth, y(entry)), 1.8f)
                drawLine(down, Offset(0f, y(stop)), Offset(plotWidth, y(stop)), 2.2f)
                drawLine(up, Offset(0f, y(target)), Offset(plotWidth, y(target)), 2.2f)
                drawCircle(signalColor, radius = 8f, center = Offset(plotWidth - 8f, y(entry)))
            }
        }

        val lastPriceY = y(candles.last().close)
        drawLine(
            Color.White.copy(alpha = 0.35f),
            Offset(0f, lastPriceY),
            Offset(plotWidth, lastPriceY),
            1.2f
        )
    }
}

@Composable
private fun RsiCanvas(closes: List<Double>) {
    val purple = Color(0xFF8E6CFF)
    val guide = Color(0xFF565B66)
    val series = mutableListOf<Double>()
    for (i in closes.indices) {
        series += if (i < 14) 50.0 else rsiValue(closes.take(i + 1), 14)
    }

    Canvas(
        Modifier
            .fillMaxWidth()
            .height(100.dp)
            .background(Color(0xFF090E16), RoundedCornerShape(10.dp))
    ) {
        fun y(v: Double): Float = ((100.0 - v) / 100.0 * size.height).toFloat()
        drawLine(guide, Offset(0f, y(70.0)), Offset(size.width, y(70.0)), 1f)
        drawLine(guide, Offset(0f, y(30.0)), Offset(size.width, y(30.0)), 1f)
        if (series.size > 1) {
            val step = size.width / series.size
            val path = Path()
            series.forEachIndexed { i, value ->
                val point = Offset(step * i + step / 2f, y(value))
                if (i == 0) path.moveTo(point.x, point.y) else path.lineTo(point.x, point.y)
            }
            drawPath(path, purple, style = Stroke(width = 2.4f))
        }
    }
}

private fun fmtChart(v: Double?): String =
    if (v == null) "-" else String.format(Locale.KOREA, "%,.2f", v)
