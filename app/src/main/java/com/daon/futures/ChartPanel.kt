package com.daon.futures

import androidx.compose.foundation.Canvas
import androidx.compose.foundation.background
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.Card
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.ui.Modifier
import androidx.compose.ui.geometry.Offset
import androidx.compose.ui.geometry.Size
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.Path
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import java.util.Locale
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
        if (d >= 0) gains += d else losses -= d
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
    val last20 = ema20.lastOrNull()
    val last50 = ema50.lastOrNull()
    val rsi = rsiValue(closes)

    Card(modifier = modifier.fillMaxWidth(), shape = RoundedCornerShape(18.dp)) {
        Column(Modifier.padding(14.dp), verticalArrangement = Arrangement.spacedBy(8.dp)) {
            Text("$symbol · $intervalLabel 차트", fontWeight = FontWeight.Bold, fontSize = 18.sp)
            if (visible.size < 2) {
                Text("차트 데이터를 불러오는 중입니다.", color = Color.Gray)
            } else {
                Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.SpaceBetween) {
                    Text("EMA20 ${fmtChart(last20)}", color = Color(0xFF4DA3FF), fontSize = 13.sp)
                    Text("EMA50 ${fmtChart(last50)}", color = Color(0xFFFFA726), fontSize = 13.sp)
                    Text("RSI ${String.format(Locale.KOREA, "%.1f", rsi)}", color = Color(0xFFB388FF), fontSize = 13.sp)
                }
                CandlestickCanvas(visible, ema20, ema50)
                RsiCanvas(closes)
            }
        }
    }
}

@Composable
private fun CandlestickCanvas(candles: List<Candle>, ema20: List<Double>, ema50: List<Double>) {
    val up = Color(0xFF34C38F)
    val down = Color(0xFFFF5B6E)
    val blue = Color(0xFF4DA3FF)
    val orange = Color(0xFFFFA726)
    val grid = Color(0xFF30343D)

    Canvas(
        Modifier
            .fillMaxWidth()
            .height(280.dp)
            .background(MaterialTheme.colorScheme.background, RoundedCornerShape(12.dp))
    ) {
        val maxPrice = candles.maxOf { it.high }
        val minPrice = candles.minOf { it.low }
        val rawRange = maxPrice - minPrice
        val range = if (rawRange <= 0.0) 1.0 else rawRange
        val pad = range * 0.08
        val top = maxPrice + pad
        val bottom = minPrice - pad
        val fullRange = top - bottom
        fun y(v: Double): Float = ((top - v) / fullRange * size.height).toFloat()

        for (g in 1..4) {
            val gy = size.height * g / 5f
            drawLine(grid, Offset(0f, gy), Offset(size.width, gy), 1f)
        }

        val step = size.width / candles.size
        val bodyWidth = max(2f, step * 0.58f)
        candles.forEachIndexed { i, c ->
            val x = step * i + step / 2f
            val color = if (c.close >= c.open) up else down
            val yo = y(c.open)
            val yc = y(c.close)
            val yh = y(c.high)
            val yl = y(c.low)
            drawLine(color, Offset(x, yh), Offset(x, yl), 1.5f)
            val bodyTop = min(yo, yc)
            val bodyHeight = max(2f, kotlin.math.abs(yc - yo))
            drawRect(color, Offset(x - bodyWidth / 2f, bodyTop), Size(bodyWidth, bodyHeight))
        }

        fun drawEma(series: List<Double>, color: Color) {
            if (series.size < 2) return
            val path = Path()
            series.forEachIndexed { i, v ->
                val p = Offset(step * i + step / 2f, y(v))
                if (i == 0) path.moveTo(p.x, p.y) else path.lineTo(p.x, p.y)
            }
            drawPath(path, color, style = androidx.compose.ui.graphics.drawscope.Stroke(width = 2.5f))
        }
        drawEma(ema20, blue)
        drawEma(ema50, orange)

        val last = candles.last().close
        val ly = y(last)
        drawLine(up.copy(alpha = 0.7f), Offset(0f, ly), Offset(size.width, ly), 1.5f)
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
            .height(90.dp)
            .background(MaterialTheme.colorScheme.background, RoundedCornerShape(10.dp))
    ) {
        fun y(v: Double) = ((100.0 - v) / 100.0 * size.height).toFloat()
        drawLine(guide, Offset(0f, y(70.0)), Offset(size.width, y(70.0)), 1f)
        drawLine(guide, Offset(0f, y(30.0)), Offset(size.width, y(30.0)), 1f)
        if (series.size > 1) {
            val step = size.width / series.size
            val path = Path()
            series.forEachIndexed { i, v ->
                val p = Offset(step * i + step / 2f, y(v))
                if (i == 0) path.moveTo(p.x, p.y) else path.lineTo(p.x, p.y)
            }
            drawPath(path, purple, style = androidx.compose.ui.graphics.drawscope.Stroke(width = 2.4f))
        }
    }
}

private fun fmtChart(v: Double?): String = if (v == null) "-" else String.format(Locale.KOREA, "%,.2f", v)
