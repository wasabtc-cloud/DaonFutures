package com.daon.futures

import android.app.NotificationManager
import android.content.Context
import androidx.core.app.NotificationCompat
import androidx.glance.appwidget.updateAll
import androidx.work.CoroutineWorker
import androidx.work.WorkerParameters
import com.daon.futures.widget.DaonWidget

class SignalWorker(ctx: Context, params: WorkerParameters) : CoroutineWorker(ctx, params) {
    override suspend fun doWork(): Result = try {
        val prefs = AppStore.prefs(applicationContext)
        val market = prefs.getString("upbit_market", "KRW-BTC") ?: "KRW-BTC"
        val priorWhale = prefs.getBoolean("whale_$market", false)
        val signal = CatchWorldCryptoScanner().scan(market, priorWhale)

        prefs.edit()
            .putString("catchworld_market", market)
            .putString("catchworld_state", signal.state.name)
            .putInt("catchworld_score", signal.score)
            .putString("catchworld_reason", signal.reason.joinToString(" · "))
            .putBoolean("whale_$market", priorWhale || signal.state != CatchWorldState.WATCH)
            .putLong("catchworld_updated", System.currentTimeMillis())
            .apply()

        if (prefs.getBoolean("notifications", true) &&
            signal.state in setOf(CatchWorldState.PRE_BLUE, CatchWorldState.BLUE, CatchWorldState.EXIT_RISK)) {
            notifySignal(market, signal)
        }
        DaonWidget().updateAll(applicationContext)
        Result.success()
    } catch (_: Exception) {
        Result.retry()
    }

    private fun notifySignal(market: String, signal: CatchWorldSignal) {
        val nm = applicationContext.getSystemService(Context.NOTIFICATION_SERVICE) as NotificationManager
        val title = when (signal.state) {
            CatchWorldState.BLUE -> "🔵 $market BLUE 후보"
            CatchWorldState.PRE_BLUE -> "🟣 $market PRE-BLUE"
            CatchWorldState.EXIT_RISK -> "🔴 $market 자금이탈 위험"
            else -> "$market ${signal.state.name}"
        }
        val text = "기회점수 ${signal.score} · ${signal.reason.joinToString(" · ")}"
        nm.notify(
            (market.hashCode() xor signal.state.hashCode()),
            NotificationCompat.Builder(applicationContext, "signals")
                .setSmallIcon(android.R.drawable.ic_dialog_info)
                .setContentTitle(title)
                .setContentText(text)
                .setStyle(NotificationCompat.BigTextStyle().bigText(text))
                .setAutoCancel(true)
                .build()
        )
    }
}
