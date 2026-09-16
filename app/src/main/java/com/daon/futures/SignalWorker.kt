package com.daon.futures

import android.app.NotificationChannel
import android.app.NotificationManager
import android.content.Context
import android.os.Build
import androidx.core.app.NotificationCompat
import androidx.glance.appwidget.updateAll
import androidx.work.CoroutineWorker
import androidx.work.WorkerParameters
import com.daon.futures.widget.DaonWidget
import java.text.SimpleDateFormat
import java.util.Date
import java.util.Locale

enum class AlertTier(val prefKey: String, val label: String) {
    NORMAL(AppStore.ALERT_NORMAL, "자금유입"), ADDITIONAL(AppStore.ALERT_ADDITIONAL, "추가 자금유입"), SUPER(AppStore.ALERT_SUPER, "SUPER SIGNAL")
}

class SignalWorker(ctx: Context, params: WorkerParameters) : CoroutineWorker(ctx, params) {
    override suspend fun doWork(): Result = try {
        val p = AppStore.prefs(applicationContext); val risk = AppStore.riskStatus(applicationContext)
        if (risk.locked) { DaonWidget().updateAll(applicationContext); Result.success() } else {
            val symbol = p.getString("symbol", "BTCUSDT")!!; val sl = p.getFloat("sl", 1f).toDouble(); val tp = p.getFloat("tp", 1.5f).toDouble()
            val livePrice = BinanceApi.price(symbol); val signal = BinanceApi.analyze(symbol, sl, tp)
            val edit = p.edit().putString("last_symbol", symbol).putString("last_price", fmt(livePrice)).putString("last_updated", fmtDate(System.currentTimeMillis()))
            if (signal != null) {
                edit.putString("last_side", signal.side).putString("last_sl", fmt(signal.sl)).putString("last_tp", fmt(signal.tp)).putString("last_rsi", String.format(Locale.US, "%.1f", signal.rsi)).putString("last_reason", signal.reason).putLong("last_candle", signal.candleTime)
                val tier = classifyTier(); val signalKey = "$symbol:${signal.side}:${tier.name}:${signal.candleTime / 900000L}"; val notified = p.getString("last_notified_key", "")
                if (notified != signalKey) {
                    AppStore.addHistory(applicationContext, signal, symbol)
                    if (p.getBoolean("notifications", true) && AppStore.alertEnabled(applicationContext, tier.prefKey)) notifySignal(signal, symbol, tier)
                    edit.putString("last_notified_key", signalKey).putString("last_alert_tier", tier.name)
                }
            } else edit.putString("last_side", "WAIT").putString("last_sl", "-").putString("last_tp", "-").putString("last_rsi", "-")
            edit.apply(); DaonWidget().updateAll(applicationContext); Result.success()
        }
    } catch (_: Exception) { Result.retry() }

    private fun classifyTier(): AlertTier = AlertTier.NORMAL

    private fun notifySignal(signal: Signal, symbol: String, tier: AlertTier) {
        val nm = applicationContext.getSystemService(Context.NOTIFICATION_SERVICE) as NotificationManager
        if (Build.VERSION.SDK_INT >= 26) nm.createNotificationChannel(NotificationChannel("signals", "캐치월드 기회 알림", NotificationManager.IMPORTANCE_HIGH))
        val direction = if (signal.side == "LONG") "🟢 LONG" else "🔴 SHORT"
        val title = when (tier) { AlertTier.NORMAL -> "✓ $symbol ${tier.label} · $direction"; AlertTier.ADDITIONAL -> "✓✓ $symbol ${tier.label} · $direction"; AlertTier.SUPER -> "S $symbol ${tier.label} · $direction" }
        val text = "진입 ${fmt(signal.price)} · SL ${fmt(signal.sl)} · TP ${fmt(signal.tp)} · RSI ${String.format(Locale.KOREA, "%.1f", signal.rsi)}"
        val builder = NotificationCompat.Builder(applicationContext, "signals").setSmallIcon(android.R.drawable.ic_dialog_info).setContentTitle(title).setContentText(text).setStyle(NotificationCompat.BigTextStyle().bigText("$text\n${signal.reason}")).setAutoCancel(true)
        if (!AppStore.soundEnabled(applicationContext)) builder.setSilent(true)
        if (!AppStore.vibrateEnabled(applicationContext)) builder.setVibrate(longArrayOf(0L)) else builder.setVibrate(longArrayOf(0L, 180L, 100L, 220L))
        nm.notify((System.currentTimeMillis() % 100000).toInt(), builder.build())
    }
    private fun fmt(v: Double) = String.format(Locale.KOREA, "%,.2f", v)
    private fun fmtDate(v: Long) = SimpleDateFormat("MM/dd HH:mm", Locale.KOREA).format(Date(v))
}
