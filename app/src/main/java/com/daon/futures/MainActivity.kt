package com.daon.futures

import android.Manifest
import android.app.NotificationChannel
import android.app.NotificationManager
import android.content.Context
import android.content.pm.PackageManager
import android.os.Bundle
import androidx.activity.ComponentActivity
import androidx.activity.compose.setContent
import androidx.activity.result.contract.ActivityResultContracts
import androidx.compose.foundation.background
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import androidx.glance.appwidget.updateAll
import androidx.work.*
import com.daon.futures.widget.DaonWidget
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext
import java.text.SimpleDateFormat
import java.util.*
import java.util.concurrent.TimeUnit

class MainActivity : ComponentActivity() {
    private val notifPermission = registerForActivityResult(ActivityResultContracts.RequestPermission()) {}

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        if (android.os.Build.VERSION.SDK_INT >= 33 && checkSelfPermission(Manifest.permission.POST_NOTIFICATIONS) != PackageManager.PERMISSION_GRANTED) {
            notifPermission.launch(Manifest.permission.POST_NOTIFICATIONS)
        }
        (getSystemService(NOTIFICATION_SERVICE) as NotificationManager).createNotificationChannel(
            NotificationChannel("signals", "매매 신호", NotificationManager.IMPORTANCE_HIGH)
        )
        val req = PeriodicWorkRequestBuilder<SignalWorker>(15, TimeUnit.MINUTES)
            .setConstraints(Constraints.Builder().setRequiredNetworkType(NetworkType.CONNECTED).build())
            .build()
        WorkManager.getInstance(this).enqueueUniquePeriodicWork("daon-signal", ExistingPeriodicWorkPolicy.UPDATE, req)
        setContent { DaonApp() }
    }
}

private val Green = Color(0xFF19D38A)
private val Red = Color(0xFFFF4D63)
private val Blue = Color(0xFF35A7FF)
private val Orange = Color(0xFFFFA000)
private val Purple = Color(0xFFA875FF)
private val Muted = Color(0xFF9BA6B5)

@Composable
fun DaonApp() {
    val context = LocalContext.current
    val prefs = remember { AppStore.prefs(context) }
    val scope = rememberCoroutineScope()

    var symbol by remember { mutableStateOf(prefs.getString("symbol", "BTCUSDT")!!) }
    var sl by remember { mutableFloatStateOf(prefs.getFloat("sl", 1f)) }
    var tp by remember { mutableFloatStateOf(prefs.getFloat("tp", 1.5f)) }
    var lev by remember { mutableIntStateOf(prefs.getInt("lev", 3)) }
    var notifications by remember { mutableStateOf(prefs.getBoolean("notifications", true)) }
    var signal by remember { mutableStateOf<Signal?>(null) }
    var price by remember { mutableDoubleStateOf(prefs.getString("last_price", null)?.replace(",", "")?.toDoubleOrNull() ?: 0.0) }
    var loading by remember { mutableStateOf(false) }
    var refreshToken by remember { mutableIntStateOf(0) }
    var chartInterval by remember { mutableStateOf("15m") }
    var chartCandles by remember { mutableStateOf<List<Candle>>(emptyList()) }
    var chartLoading by remember { mutableStateOf(false) }
    var chartError by remember { mutableStateOf<String?>(null) }
    val history = remember(refreshToken) { AppStore.history(context) }

    LaunchedEffect(symbol, chartInterval) {
        chartLoading = true
        chartError = null
        try {
            chartCandles = withContext(Dispatchers.IO) { BinanceApi.candles(symbol, chartInterval, 100) }
            if (chartCandles.isNotEmpty()) price = chartCandles.last().close
        } catch (e: Exception) {
            chartError = e.message ?: "차트 로딩 오류"
        } finally {
            chartLoading = false
        }
    }

    val closes = chartCandles.takeLast(60).map { it.close }
    val e20 = emaSeries(closes, 20).lastOrNull()
    val e50 = emaSeries(closes, 50).lastOrNull()
    val rsi = if (closes.size > 14) rsiValue(closes) else null
    val trend = when {
        e20 == null || e50 == null -> "대기"
        e20 > e50 -> "상승"
        else -> "하락"
    }

    MaterialTheme(
        colorScheme = darkColorScheme(
            primary = Color(0xFF6C63FF),
            background = Color(0xFF070B12),
            surface = Color(0xFF111722),
            surfaceVariant = Color(0xFF171F2C)
        )
    ) {
        LazyColumn(
            Modifier.fillMaxSize().background(MaterialTheme.colorScheme.background).padding(horizontal = 14.dp),
            contentPadding = PaddingValues(top = 18.dp, bottom = 28.dp),
            verticalArrangement = Arrangement.spacedBy(12.dp)
        ) {
            item {
                Column(verticalArrangement = Arrangement.spacedBy(3.dp)) {
                    Row(verticalAlignment = Alignment.CenterVertically) {
                        Text("다온이 선물매매", fontSize = 28.sp, fontWeight = FontWeight.ExtraBold)
                        Spacer(Modifier.width(8.dp))
                        Text("v2.4", color = Color(0xFF8B7CFF), fontSize = 24.sp, fontWeight = FontWeight.Bold)
                    }
                    Text("실시간 차트 · EMA20/50 · RSI · LONG/SHORT 후보", color = Muted, fontSize = 13.sp)
                }
            }

            item {
                Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                    listOf("BTCUSDT", "ETHUSDT").forEach { s ->
                        FilterChip(
                            modifier = Modifier.weight(1f),
                            selected = symbol == s,
                            onClick = {
                                symbol = s
                                save(context, symbol, sl, tp, lev, notifications)
                                refreshToken++
                            },
                            label = { Text(s, fontWeight = FontWeight.Bold) }
                        )
                    }
                }
            }

            item {
                DashboardSummary(price = price, trend = trend, ema20 = e20, ema50 = e50, rsi = rsi)
            }

            item {
                Card(shape = RoundedCornerShape(20.dp), colors = CardDefaults.cardColors(containerColor = Color(0xFF101722))) {
                    Column(Modifier.padding(12.dp), verticalArrangement = Arrangement.spacedBy(8.dp)) {
                        Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.spacedBy(7.dp)) {
                            listOf("15m" to "15분", "1h" to "1시간", "4h" to "4시간").forEach { (key, label) ->
                                FilterChip(
                                    modifier = Modifier.weight(1f),
                                    selected = chartInterval == key,
                                    onClick = { chartInterval = key },
                                    label = { Text(label) }
                                )
                            }
                        }
                        when {
                            chartLoading -> LinearProgressIndicator(Modifier.fillMaxWidth())
                            chartError != null -> Text("차트 불러오기 실패: $chartError", color = Red, fontSize = 12.sp)
                            else -> MarketChartCard(
                                symbol,
                                when (chartInterval) { "1h" -> "1시간"; "4h" -> "4시간"; else -> "15분" },
                                chartCandles
                            )
                        }
                    }
                }
            }

            item {
                Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                    MetricCard("EMA20", e20?.let { fmt(it) } ?: "-", Blue, Modifier.weight(1f))
                    MetricCard("EMA50", e50?.let { fmt(it) } ?: "-", Orange, Modifier.weight(1f))
                    MetricCard("RSI", rsi?.let { String.format(Locale.KOREA, "%.1f", it) } ?: "-", Purple, Modifier.weight(1f))
                }
            }

            item {
                SignalCard(signal = signal, trend = trend, loading = loading) {
                    scope.launch {
                        loading = true
                        save(context, symbol, sl, tp, lev, notifications)
                        try {
                            price = withContext(Dispatchers.IO) { BinanceApi.price(symbol) }
                            signal = withContext(Dispatchers.IO) { BinanceApi.analyze(symbol, sl.toDouble(), tp.toDouble()) }
                            chartCandles = withContext(Dispatchers.IO) { BinanceApi.candles(symbol, chartInterval, 100) }
                            val e = prefs.edit()
                                .putString("last_symbol", symbol)
                                .putString("last_price", fmt(price))
                                .putString("last_updated", fmtDate(System.currentTimeMillis()))
                            signal?.let {
                                e.putString("last_side", it.side)
                                    .putString("last_sl", fmt(it.sl))
                                    .putString("last_tp", fmt(it.tp))
                                    .putString("last_rsi", String.format(Locale.US, "%.1f", it.rsi))
                                    .putString("last_reason", it.reason)
                                    .putLong("last_candle", it.candleTime)
                                AppStore.addHistory(context, it, symbol)
                            } ?: run {
                                e.putString("last_side", "WAIT")
                                    .putString("last_sl", "-")
                                    .putString("last_tp", "-")
                                    .putString("last_rsi", "-")
                            }
                            e.apply()
                            DaonWidget().updateAll(context)
                            refreshToken++
                        } finally {
                            loading = false
                        }
                    }
                }
            }

            item {
                SettingsCard(
                    sl = sl,
                    tp = tp,
                    lev = lev,
                    notifications = notifications,
                    onSl = { sl = it },
                    onTp = { tp = it },
                    onLev = { lev = it; save(context, symbol, sl, tp, lev, notifications) },
                    onNotifications = { notifications = it; save(context, symbol, sl, tp, lev, notifications) },
                    onSave = { save(context, symbol, sl, tp, lev, notifications) }
                )
            }

            item { Text("최근 신호 기록", fontSize = 20.sp, fontWeight = FontWeight.Bold) }
            if (history.isEmpty()) {
                item { Text("아직 신호 기록이 없습니다.", color = Muted) }
            } else {
                items(history) { r ->
                    Card(shape = RoundedCornerShape(14.dp), modifier = Modifier.fillMaxWidth()) {
                        Column(Modifier.padding(14.dp)) {
                            Text("${r.symbol}  ${if (r.side == "LONG") "▲ LONG" else "▼ SHORT"}", color = if (r.side == "LONG") Green else Red, fontWeight = FontWeight.Bold)
                            Text("진입 ${fmt(r.price)} · SL ${fmt(r.sl)} · TP ${fmt(r.tp)}")
                            Text("RSI ${String.format(Locale.KOREA, "%.1f", r.rsi)} · ${fmtDate(r.timestamp)}", fontSize = 12.sp, color = Muted)
                        }
                    }
                }
            }

            item {
                val risk = AppStore.riskStatus(context)
                Card(shape = RoundedCornerShape(18.dp)) {
                    Column(Modifier.padding(16.dp), verticalArrangement = Arrangement.spacedBy(9.dp)) {
                        Text("매매 안전장치", fontWeight = FontWeight.Bold, fontSize = 18.sp)
                        Text("오늘 순손익 ${risk.pnl.toLocaleWon()} · 연속손실 ${risk.consecutiveLosses}/2")
                        Text(
                            if (risk.locked) "오늘 매매 종료 — 안전장치 작동" else "거래 가능 · 1회 -5,000원 권장 / 하루 -20,000원 제한",
                            color = if (risk.locked) Red else Green,
                            fontWeight = FontWeight.Bold,
                            fontSize = 13.sp
                        )
                        Row(horizontalArrangement = Arrangement.spacedBy(6.dp)) {
                            OutlinedButton(onClick = { AppStore.recordResult(context, false, 5000); refreshToken++ }) { Text("-5천") }
                            OutlinedButton(onClick = { AppStore.recordResult(context, true, 5000); refreshToken++ }) { Text("+5천") }
                            OutlinedButton(onClick = { AppStore.resetRisk(context); refreshToken++ }) { Text("초기화") }
                        }
                    }
                }
            }

            item {
                Text("※ LONG/SHORT 표시는 후보 신호입니다. 자동 주문 기능이 아니며 실제 주문은 거래소에서 직접 확인해야 합니다.", color = Muted, fontSize = 11.sp)
            }
        }
    }
}

@Composable
private fun DashboardSummary(price: Double, trend: String, ema20: Double?, ema50: Double?, rsi: Double?) {
    Card(shape = RoundedCornerShape(20.dp), colors = CardDefaults.cardColors(containerColor = Color(0xFF111927))) {
        Column(Modifier.padding(16.dp), verticalArrangement = Arrangement.spacedBy(12.dp)) {
            Text("현재가", color = Muted, fontSize = 12.sp)
            Text(if (price > 0) fmt(price) else "-", color = Green, fontSize = 34.sp, fontWeight = FontWeight.ExtraBold)
            HorizontalDivider(color = Color(0xFF273142))
            Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.SpaceBetween) {
                Column { Text("현재 추세", color = Muted, fontSize = 12.sp); Text(when (trend) { "상승" -> "↑ 상승"; "하락" -> "↓ 하락"; else -> "— 대기" }, color = if (trend == "상승") Green else if (trend == "하락") Red else Muted, fontWeight = FontWeight.Bold) }
                Column(horizontalAlignment = Alignment.End) { Text("EMA 간격", color = Muted, fontSize = 12.sp); Text(if (ema20 != null && ema50 != null) fmt(ema20 - ema50) else "-", fontWeight = FontWeight.Bold) }
                Column(horizontalAlignment = Alignment.End) { Text("RSI", color = Muted, fontSize = 12.sp); Text(rsi?.let { String.format(Locale.KOREA, "%.1f", it) } ?: "-", color = Purple, fontWeight = FontWeight.Bold) }
            }
        }
    }
}

@Composable
private fun MetricCard(title: String, value: String, color: Color, modifier: Modifier = Modifier) {
    Card(modifier = modifier, shape = RoundedCornerShape(16.dp), colors = CardDefaults.cardColors(containerColor = Color(0xFF121A27))) {
        Column(Modifier.padding(12.dp)) {
            Text(title, color = Muted, fontSize = 11.sp)
            Text(value, color = color, fontWeight = FontWeight.Bold, fontSize = 13.sp)
        }
    }
}

@Composable
private fun SignalCard(signal: Signal?, trend: String, loading: Boolean, onAnalyze: () -> Unit) {
    val side = signal?.side ?: "WAIT"
    val color = when (side) { "LONG" -> Green; "SHORT" -> Red; else -> Muted }
    Card(shape = RoundedCornerShape(20.dp), colors = CardDefaults.cardColors(containerColor = Color(0xFF111927))) {
        Column(Modifier.padding(16.dp), verticalArrangement = Arrangement.spacedBy(8.dp)) {
            Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.SpaceBetween, verticalAlignment = Alignment.CenterVertically) {
                Column {
                    Text("현재 신호", color = Muted, fontSize = 12.sp)
                    Text(when (side) { "LONG" -> "▲ LONG"; "SHORT" -> "▼ SHORT"; else -> "● 대기" }, color = color, fontSize = 28.sp, fontWeight = FontWeight.ExtraBold)
                    Text(if (side == "WAIT") "$trend 추세 확인 중" else signal?.reason ?: "", color = Muted, fontSize = 12.sp)
                }
                Button(enabled = !loading, onClick = onAnalyze) { Text(if (loading) "분석 중…" else "지금 분석") }
            }
            signal?.let {
                HorizontalDivider(color = Color(0xFF273142))
                Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.SpaceBetween) {
                    Text("진입 ${fmt(it.price)}")
                    Text("SL ${fmt(it.sl)}", color = Red)
                    Text("TP ${fmt(it.tp)}", color = Green)
                }
            }
        }
    }
}

@Composable
private fun SettingsCard(
    sl: Float,
    tp: Float,
    lev: Int,
    notifications: Boolean,
    onSl: (Float) -> Unit,
    onTp: (Float) -> Unit,
    onLev: (Int) -> Unit,
    onNotifications: (Boolean) -> Unit,
    onSave: () -> Unit
) {
    Card(shape = RoundedCornerShape(20.dp)) {
        Column(Modifier.padding(16.dp), verticalArrangement = Arrangement.spacedBy(8.dp)) {
            Text("매매 설정", fontWeight = FontWeight.Bold, fontSize = 18.sp)
            Text("손절 ${String.format(Locale.KOREA, "%.1f", sl)}% · 익절 ${String.format(Locale.KOREA, "%.1f", tp)}% · 레버리지 ${lev}배", color = Muted)
            Text("손절", fontSize = 12.sp)
            Slider(value = sl, onValueChange = onSl, valueRange = 0.5f..3f, steps = 5, onValueChangeFinished = onSave)
            Text("익절", fontSize = 12.sp)
            Slider(value = tp, onValueChange = onTp, valueRange = 0.5f..5f, steps = 9, onValueChangeFinished = onSave)
            Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                listOf(1, 2, 3).forEach { i -> FilterChip(selected = lev == i, onClick = { onLev(i) }, label = { Text("${i}배") }) }
            }
            Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.SpaceBetween, verticalAlignment = Alignment.CenterVertically) {
                Column { Text("푸시 알림", fontWeight = FontWeight.Bold); Text("신호 발생 시 알림", fontSize = 11.sp, color = Muted) }
                Switch(checked = notifications, onCheckedChange = onNotifications)
            }
        }
    }
}

fun save(c: Context, symbol: String, sl: Float, tp: Float, lev: Int, notifications: Boolean) = AppStore.saveSettings(c, symbol, sl, tp, lev, notifications)
fun fmt(v: Double) = String.format(Locale.KOREA, "%,.2f", v)
fun fmtDate(v: Long) = SimpleDateFormat("MM/dd HH:mm", Locale.KOREA).format(Date(v))
private fun Int.toLocaleWon(): String = String.format(Locale.KOREA, "%+,d원", this)
