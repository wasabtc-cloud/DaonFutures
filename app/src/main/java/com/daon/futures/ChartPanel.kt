package com.daon.futures

import androidx.compose.foundation.Canvas
import androidx.compose.foundation.background
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.Card
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.ui.Modifier
import androidx.compose.ui.geometry.Offset
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
    val out = mutableListOf(values.first())
    var ema = values.first()
    for (i in 1 until values.size) {
        ema = values[i] * k + ema * (1.0 - k)
        out += ema
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

private data class MoneyFlowMark(val index: Int, val level: Int)

private fun moneyFlowMarks(candles: List<Candle>): List<MoneyFlowMark> {
    if (candles.size < 12) return emptyList()
    val ranges = candles.map { max(0.0, it.high - it.low) }
    val marks = mutableListOf<MoneyFlowMark>()
    for (i in 10 until candles.size) {
        val base = ranges.subList(i - 10, i).average().coerceAtLeast(1e-9)
        val impulse = ranges[i] / base
        val body = abs(candles[i].close - candles[i].open) / base
        val level = when {
            impulse >= 2.8 && body >= 1.0 -> 3
            impulse >= 2.1 && body >= 0.65 -> 2
            impulse >= 1.6 && body >= 0.35 -> 1
            else -> 0
        }
        if (level > 0) marks += MoneyFlowMark(i, level)
    }
    return marks.takeLast(6)
}

@Composable
fun MarketChartCard(
    symbol: String,
    intervalLabel: String,
    candles: List<Candle>,
    modifier: Modifier = Modifier,
    exchange: String = "MARKET"
) {
    val visible = candles.takeLast(60)
    val closes = visible.map { it.close }
    val ema20 = emaSeries(closes, 20)
    val ema50 = emaSeries(closes, 50)
    val rsi = rsiValue(closes)
    val marks = moneyFlowMarks(visible)
    val latestLevel = marks.lastOrNull()?.level ?: 0

    Card(modifier.fillMaxWidth(), shape = RoundedCornerShape(18.dp)) {
        Column(Modifier.padding(14.dp), verticalArrangement = Arrangement.spacedBy(8.dp)) {
            Text("$symbol · $intervalLabel · $exchange", fontWeight = FontWeight.Bold, fontSize = 18.sp)
            if (visible.size < 2) {
                Text("차트 데이터를 불러오는 중입니다.", color = Color.Gray)
            } else {
                Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.SpaceBetween) {
                    Text("EMA20 ${fmtChart(ema20.lastOrNull())}", color = Color(0xFF35A7FF), fontSize = 13.sp)
                    Text("EMA50 ${fmtChart(ema50.lastOrNull())}", color = Color(0xFFFFA000), fontSize = 13.sp)
                    Text("RSI ${String.format(Locale.KOREA, "%.1f", rsi)}", color = Color(0xFFA875FF), fontSize = 13.sp)
                }
                Text("자금유입 연구표시 · ✓ 초기  ✓✓ 추가  ★ 강한 유입", color = Color(0xFF21D58B), fontWeight = FontWeight.Bold, fontSize = 12.sp)
                if (latestLevel == 3) {
                    Text("S 후보 · 강한 움직임 감지 (검증 중)", color = Color(0xFFFFC107), fontWeight = FontWeight.ExtraBold, fontSize = 14.sp)
                }
                CandlestickCanvas(visible, ema20, ema50, marks)
                Text("RSI 14 ${String.format(Locale.KOREA, "%.2f", rsi)}", color = Color(0xFFA875FF), fontSize = 13.sp)
                RsiCanvas(closes)
            }
        }
    }
}

@Composable
private fun CandlestickCanvas(candles: List<Candle>, ema20: List<Double>, ema50: List<Double>, marks: List<MoneyFlowMark>) {
    Canvas(Modifier.fillMaxWidth().height(360.dp).background(Color(0xFF090E16), RoundedCornerShape(12.dp))) {
        val up = Color(0xFF18C98B)
        val down = Color(0xFFFF4058)
        val maxP = candles.maxOf { it.high }
        val minP = candles.minOf { it.low }
        val range = (maxP - minP).takeIf { it > 0.0 } ?: 1.0
        val top = maxP + range * 0.1
        val bottom = minP - range * 0.1
        fun y(v: Double) = ((top - v) / (top - bottom) * size.height).toFloat()
        val plotWidth = size.width * 0.9f
        val step = plotWidth / candles.size
        val bodyWidth = max(2f, step * 0.58f)

        for (g in 1..5) {
            val gy = size.height * g / 6f
            drawLine(Color(0xFF29313D), Offset(0f, gy), Offset(plotWidth, gy), 1f)
        }
        candles.forEachIndexed { i, candle ->
            val x = step * i + step / 2f
            val color = if (candle.close >= candle.open) up else down
            val openY = y(candle.open)
            val closeY = y(candle.close)
            drawLine(color, Offset(x, y(candle.high)), Offset(x, y(candle.low)), 1.4f)
            drawRect(color, Offset(x - bodyWidth / 2f, min(openY, closeY)), androidx.compose.ui.geometry.Size(bodyWidth, max(2f, abs(closeY - openY))))
        }
        fun drawEma(series: List<Double>, color: Color) {
            if (series.size < 2) return
            val path = Path()
            series.forEachIndexed { i, value ->
                val p = Offset(step * i + step / 2f, y(value))
                if (i == 0) path.moveTo(p.x, p.y) else path.lineTo(p.x, p.y)
            }
            drawPath(path, color, style = Stroke(2.5f))
        }
        drawEma(ema20, Color(0xFF2196F3))
        drawEma(ema50, Color(0xFFFFA000))
        marks.forEach { mark ->
            if (mark.index < candles.size) {
                val x = step * mark.index + step / 2f
                val yy = (y(candles[mark.index].low) + 15f).coerceAtMost(size.height - 12f)
                val color = if (mark.level == 3) Color(0xFFFFC107) else up
                val radius = when (mark.level) { 3 -> 8f; 2 -> 6f; else -> 4.5f }
                drawCircle(color, radius, Offset(x, yy))
            }
        }
        val lastY = y(candles.last().close)
        drawLine(Color.White.copy(alpha = 0.35f), Offset(0f, lastY), Offset(plotWidth, lastY), 1.2f)
    }
}

@Composable
private fun RsiCanvas(closes: List<Double>) {
    val series = closes.indices.map { i -> if (i < 14) 50.0 else rsiValue(closes.take(i + 1), 14) }
    Canvas(Modifier.fillMaxWidth().height(100.dp).background(Color(0xFF090E16), RoundedCornerShape(10.dp))) {
        fun y(v: Double) = ((100.0 - v) / 100.0 * size.height).toFloat()
        drawLine(Color(0xFF565B66), Offset(0f, y(70.0)), Offset(size.width, y(70.0)), 1f)
        drawLine(Color(0xFF565B66), Offset(0f, y(30.0)), Offset(size.width, y(30.0)), 1f)
        if (series.size > 1) {
            val step = size.width / series.size
            val path = Path()
            series.forEachIndexed { i, value ->
                val p = Offset(step * i + step / 2f, y(value))
                if (i == 0) path.moveTo(p.x, p.y) else path.lineTo(p.x, p.y)
            }
            drawPath(path, Color(0xFF8E6CFF), style = Stroke(2.4f))
        }
    }
}

private fun fmtChart(value: Double?): String = if (value == null) "-" else String.format(Locale.KOREA, "%,.2f", value)
