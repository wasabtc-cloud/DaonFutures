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
    val entry: Double,
    val stop: Double,
    val target2R: Double
)

private fun oneCandleZone(candles: List<Candle>, ema20: List<Double>, ema50: List<Double>): OneCandleZone? {
    if (candles.size < 22 || ema20.isEmpty() || ema50.isEmpty()) return null
    val bullish = ema20.last() > ema50.last()
    val start = maxOf(0, candles.size - 21)
    val end = candles.size - 1
    val indexed = (start until end).map { it to candles[it] }
    val key = if (bullish) {
        indexed.filter { (_, c) -> c.close < c.open }.maxByOrNull { (_, c) -> c.high }
    } else {
        indexed.filter { (_, c) -> c.close > c.open }.minByOrNull { (_, c) -> c.low }
    } ?: return null

    val (idx, candle) = key
    val low = minOf(candle.open, candle.close)
    val high = maxOf(candle.open, candle.close)
    val last = candles.last()
    val retested = last.low <= high && last.high >= low
    val entry = last.close
    val stop = if (bullish) low else high
    val risk = if (bullish) entry - stop else stop - entry
    val target = if (risk > 0.0) {
        if (bullish) entry + risk * 2.0 else entry - risk * 2.0
    } else entry

    return OneCandleZone(
        index = idx,
        low = low,
        high = high,
        side = if (bullish) "LONG" else "SHORT",
        retested = retested,
        entry = entry,
        stop = stop,
        target2R = target
    )
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
    val ema20 = emaSeries(closes, 20)
    val ema50 = emaSeries(closes, 50)
    val rsi = rsiValue(closes)
    val zone = oneCandleZone(visible, ema20, ema50)

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
                    Text("EMA20 ${fmtChart(ema20.lastOrNull())}", color = Color(0xFF35A7FF), fontSize = 13.sp)
                    Text("EMA50 ${fmtChart(ema50.lastOrNull())}", color = Color(0xFFFFA000), fontSize = 13.sp)
                    Text("RSI ${String.format(Locale.KOREA, "%.1f", rsi)}", color = Color(0xFFA875FF), fontSize = 13.sp)
                }

                zone?.let {
                    val sideColor = if (it.side == "LONG") Color(0xFF21D58B) else Color(0xFFFF4058)
                    val state = if (it.retested) "리테스트 감지" else "리테스트 대기"
                    Text(
                        "One Candle ${it.side} · 기준 ${fmtChart(it.low)} ~ ${fmtChart(it.high)} · $state",
                        color = sideColor,
                        fontWeight = FontWeight.Bold,
                        fontSize = 12.sp
                    )
                } ?: Text("One Candle · 기준 캔들 탐색 중", color = Color.Gray, fontSize = 12.sp)

                CandlestickCanvas(visible, ema20, ema50, zone)

                zone?.let {
                    if (it.retested) {
                        Text(
                            "진입 후보 ${fmtChart(it.entry)} · SL ${fmtChart(it.stop)} · 2R ${fmtChart(it.target2R)}",
                            color = if (it.side == "LONG") Color(0xFF21D58B) else Color(0xFFFF4058),
                            fontWeight = FontWeight.Bold,
                            fontSize = 12.sp
                        )
                    }
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
    ema20: List<Double>,
    ema50: List<Double>,
    zone: OneCandleZone?
) {
    val up = Color(0xFF18C98B)
    val down = Color(0xFFFF4058)
    val blue = Color(0xFF2196F3)
    val orange = Color(0xFFFFA000)
    val grid = Color(0xFF29313D)

    Canvas(
        Modifier.fillMaxWidth().height(330.dp).background(Color(0xFF090E16), RoundedCornerShape(12.dp))
    ) {
        val extras = buildList {
            zone?.let { add(it.low); add(it.high); if (it.retested) { add(it.stop); add(it.target2R) } }
        }
        val maxPrice = max(candles.maxOf { it.high }, extras.maxOrNull() ?: candles.maxOf { it.high })
        val minPrice = min(candles.minOf { it.low }, extras.minOrNull() ?: candles.minOf { it.low })
        val rawRange = maxPrice - minPrice
        val range = if (rawRange <= 0.0) 1.0 else rawRange
        val pad = range * 0.12
        val top = maxPrice + pad
        val bottom = minPrice - pad
        val fullRange = top - bottom

        fun y(value: Double): Float = ((top - value) / fullRange * size.height).toFloat()

        for (g in 1..5) {
            val gy = size.height * g / 6f
            drawLine(grid, Offset(0f, gy), Offset(size.width, gy), 1f)
        }

        val step = size.width / candles.size
        val bodyWidth = max(2f, step * 0.58f)

        zone?.let {
            val zoneColor = if (it.side == "LONG") up else down
            val left = (step * it.index).coerceAtLeast(0f)
            val topY = min(y(it.high), y(it.low))
            val bottomY = max(y(it.high), y(it.low))
            drawRect(
                color = zoneColor.copy(alpha = 0.20f),
                topLeft = Offset(left, topY),
                size = Size(size.width - left, max(3f, bottomY - topY))
            )
            drawLine(zoneColor, Offset(left, topY), Offset(size.width, topY), 2f)
            drawLine(zoneColor, Offset(left, bottomY), Offset(size.width, bottomY), 2f)
        }

        candles.forEachIndexed { i, candle ->
            val x = step * i + step / 2f
            val candleColor = if (candle.close >= candle.open) up else down
            val openY = y(candle.open)
            val closeY = y(candle.close)
            drawLine(candleColor, Offset(x, y(candle.high)), Offset(x, y(candle.low)), 1.4f)
            drawRect(
                candleColor,
                Offset(x - bodyWidth / 2f, min(openY, closeY)),
                Size(bodyWidth, max(2f, abs(closeY - openY)))
            )
        }

        fun drawEma(series: List<Double>, color: Color) {
            if (series.size >= 2) {
                val path = Path()
                series.forEachIndexed { i, value ->
                    val point = Offset(step * i + step / 2f, y(value))
                    if (i == 0) path.moveTo(point.x, point.y) else path.lineTo(point.x, point.y)
                }
                drawPath(path, color, style = Stroke(width = 2.5f))
            }
        }
        drawEma(ema20, blue)
        drawEma(ema50, orange)

        zone?.takeIf { it.retested }?.let {
            val sideColor = if (it.side == "LONG") up else down
            val entryY = y(it.entry)
            val stopY = y(it.stop)
            val tpY = y(it.target2R)
            drawLine(sideColor, Offset(0f, entryY), Offset(size.width, entryY), 1.8f)
            drawLine(down, Offset(0f, stopY), Offset(size.width, stopY), 2.2f)
            drawLine(up, Offset(0f, tpY), Offset(size.width, tpY), 2.2f)
            drawCircle(sideColor, radius = 8f, center = Offset(size.width - 12f, entryY))
        }

        val lastPriceY = y(candles.last().close)
        drawLine(Color.White.copy(alpha = 0.35f), Offset(0f, lastPriceY), Offset(size.width, lastPriceY), 1.2f)
    }
}

@Composable
private fun RsiCanvas(closes: List<Double>) {
    val purple = Color(0xFF8E6CFF)
    val guide = Color(0xFF565B66)
    val series = mutableListOf<Double>()
    for (i in closes.indices) series += if (i < 14) 50.0 else rsiValue(closes.take(i + 1), 14)

    Canvas(Modifier.fillMaxWidth().height(100.dp).background(Color(0xFF090E16), RoundedCornerShape(10.dp))) {
        fun y(value: Double): Float = ((100.0 - value) / 100.0 * size.height).toFloat()
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

private fun fmtChart(value: Double?): String = if (value == null) "-" else String.format(Locale.KOREA, "%,.2f", value)
