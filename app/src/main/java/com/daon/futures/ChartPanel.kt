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

    Card(modifier = modifier.fillMaxWidth(), shape = RoundedCornerShape(18.dp)) {
        Column(
            Modifier.padding(14.dp),
            verticalArrangement = Arrangement.spacedBy(8.dp)
        ) {
            Text(
                "$symbol · $intervalLabel · BINANCE",
                fontWeight = FontWeight.Bold,
                fontSize = 18.sp
            )

            if (visible.size < 2) {
                Text("차트 데이터를 불러오는 중입니다.", color = Color.Gray)
            } else {
                Row(
                    Modifier.fillMaxWidth(),
                    horizontalArrangement = Arrangement.SpaceBetween
                ) {
                    Text("EMA20 ${fmtChart(ema20.lastOrNull())}", color = Color(0xFF35A7FF), fontSize = 13.sp)
                    Text("EMA50 ${fmtChart(ema50.lastOrNull())}", color = Color(0xFFFFA000), fontSize = 13.sp)
                    Text("RSI ${String.format(Locale.KOREA, "%.1f", rsi)}", color = Color(0xFFA875FF), fontSize = 13.sp)
                }

                CandlestickCanvas(visible, ema20, ema50)

                Text(
                    "RSI 14  ${String.format(Locale.KOREA, "%.2f", rsi)}",
                    color = Color(0xFFA875FF),
                    fontSize = 13.sp
                )
                RsiCanvas(closes)

                Row(
                    Modifier.fillMaxWidth(),
                    horizontalArrangement = Arrangement.SpaceBetween
                ) {
                    Text("▲ LONG 후보", color = Color(0xFF21D58B), fontWeight = FontWeight.Bold, fontSize = 12.sp)
                    Text("▼ SHORT 후보", color = Color(0xFFFF4058), fontWeight = FontWeight.Bold, fontSize = 12.sp)
                }
            }
        }
    }
}

@Composable
private fun CandlestickCanvas(
    candles: List<Candle>,
    ema20: List<Double>,
    ema50: List<Double>
) {
    val up = Color(0xFF18C98B)
    val down = Color(0xFFFF4058)
    val blue = Color(0xFF2196F3)
    val orange = Color(0xFFFFA000)
    val grid = Color(0xFF29313D)

    Canvas(
        Modifier
            .fillMaxWidth()
            .height(330.dp)
            .background(Color(0xFF090E16), RoundedCornerShape(12.dp))
    ) {
        val maxPrice = candles.maxOf { it.high }
        val minPrice = candles.minOf { it.low }
        val rawRange = maxPrice - minPrice
        val range = if (rawRange <= 0.0) 1.0 else rawRange
        val pad = range * 0.12
        val top = maxPrice + pad
        val bottom = minPrice - pad
        val fullRange = top - bottom

        fun y(value: Double): Float = ((top - value) / fullRange * size.height).toFloat()

        for (g in 1..5) {
            val gy = size.height * g / 6f
            drawLine(
                color = grid,
                start = Offset(0f, gy),
                end = Offset(size.width, gy),
                strokeWidth = 1f
            )
        }

        val step = size.width / candles.size
        val bodyWidth = max(2f, step * 0.58f)

        candles.forEachIndexed { i, candle ->
            val x = step * i + step / 2f
            val candleColor = if (candle.close >= candle.open) up else down
            val openY = y(candle.open)
            val closeY = y(candle.close)

            drawLine(
                color = candleColor,
                start = Offset(x, y(candle.high)),
                end = Offset(x, y(candle.low)),
                strokeWidth = 1.4f
            )

            drawRect(
                color = candleColor,
                topLeft = Offset(x - bodyWidth / 2f, min(openY, closeY)),
                size = Size(bodyWidth, max(2f, abs(closeY - openY)))
            )
        }

        fun drawEma(series: List<Double>, color: Color) {
            if (series.size >= 2) {
                val path = Path()
                series.forEachIndexed { i, value ->
                    val point = Offset(step * i + step / 2f, y(value))
                    if (i == 0) path.moveTo(point.x, point.y) else path.lineTo(point.x, point.y)
                }
                drawPath(path = path, color = color, style = Stroke(width = 2.5f))
            }
        }

        drawEma(ema20, blue)
        drawEma(ema50, orange)

        // EMA20/EMA50 교차 지점을 LONG/SHORT 후보로 표시합니다.
        for (i in 1 until candles.size) {
            val previousGap = ema20[i - 1] - ema50[i - 1]
            val currentGap = ema20[i] - ema50[i]
            val x = step * i + step / 2f

            if (previousGap <= 0.0 && currentGap > 0.0) {
                val markerY = (y(candles[i].low) + 18f).coerceAtMost(size.height - 10f)
                drawCircle(color = up, radius = 8f, center = Offset(x, markerY))
                drawLine(
                    color = up,
                    start = Offset(x, markerY - 18f),
                    end = Offset(x, markerY - 4f),
                    strokeWidth = 5f
                )
            }

            if (previousGap >= 0.0 && currentGap < 0.0) {
                val markerY = (y(candles[i].high) - 18f).coerceAtLeast(10f)
                drawCircle(color = down, radius = 8f, center = Offset(x, markerY))
                drawLine(
                    color = down,
                    start = Offset(x, markerY + 4f),
                    end = Offset(x, markerY + 18f),
                    strokeWidth = 5f
                )
            }
        }

        val lastPriceY = y(candles.last().close)
        drawLine(
            color = up.copy(alpha = 0.7f),
            start = Offset(0f, lastPriceY),
            end = Offset(size.width, lastPriceY),
            strokeWidth = 1.4f
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
        fun y(value: Double): Float = ((100.0 - value) / 100.0 * size.height).toFloat()

        drawLine(
            color = guide,
            start = Offset(0f, y(70.0)),
            end = Offset(size.width, y(70.0)),
            strokeWidth = 1f
        )
        drawLine(
            color = guide,
            start = Offset(0f, y(30.0)),
            end = Offset(size.width, y(30.0)),
            strokeWidth = 1f
        )

        if (series.size > 1) {
            val step = size.width / series.size
            val path = Path()
            series.forEachIndexed { i, value ->
                val point = Offset(step * i + step / 2f, y(value))
                if (i == 0) path.moveTo(point.x, point.y) else path.lineTo(point.x, point.y)
            }
            drawPath(path = path, color = purple, style = Stroke(width = 2.4f))
        }
    }
}

private fun fmtChart(value: Double?): String =
    if (value == null) "-" else String.format(Locale.KOREA, "%,.2f", value)
