package com.daon.futures

import android.app.NotificationManager
import android.content.Context
import androidx.core.app.NotificationCompat
import androidx.glance.appwidget.updateAll
import androidx.work.CoroutineWorker
import androidx.work.WorkerParameters
import com.daon.futures.widget.DaonWidget
import org.json.JSONArray
import org.json.JSONObject

class SignalWorker(ctx: Context, params: WorkerParameters) : CoroutineWorker(ctx, params) {
    override suspend fun doWork(): Result = try {
        val prefs = AppStore.prefs(applicationContext)
        val markets = UpbitPublicApi.krwMarkets()
        val cursor = prefs.getInt("radar_cursor", 0).coerceAtLeast(0)
        // Upbit rate limits + Android background budget: rotate through the universe each run.
        val batch = 24
        val selected = (0 until minOf(batch, markets.size)).map { markets[(cursor + it) % markets.size] }
        val results = mutableListOf<CatchWorldScanResult>()
        for (market in selected) {
            try {
                val prior = prefs.getBoolean("whale_$market", false)
                val r = CatchWorldCryptoScanner().scan(market, prior)
                results += r
                val active = r.signal.state in setOf(CatchWorldState.WHALE, CatchWorldState.HOLDING, CatchWorldState.PRE_BLUE, CatchWorldState.BLUE)
                val exit = r.signal.state == CatchWorldState.EXIT_RISK
                if (active) prefs.edit().putBoolean("whale_$market", true).putLong("whale_seen_$market", System.currentTimeMillis()).apply()
                if (exit) prefs.edit().putBoolean("whale_$market", false).apply()
                if (prefs.getBoolean("notifications", true) && r.signal.state in setOf(CatchWorldState.PRE_BLUE, CatchWorldState.BLUE, CatchWorldState.EXIT_RISK)) notifySignal(market, r.signal)
            } catch (_: Exception) { }
        }
        val ranked = results.sortedByDescending { it.signal.score }.take(20)
        val arr = JSONArray()
        ranked.forEach { r ->
            arr.put(JSONObject().apply {
                put("market", r.snapshot.market); put("state", r.signal.state.name); put("score", r.signal.score)
                put("price", r.snapshot.price); put("vr", r.snapshot.volumeRatio1h); put("rsi", r.snapshot.rsi14)
                put("ret1h", r.snapshot.return1h); put("reason", r.signal.reason.joinToString(" · "))
            })
        }
        val best = ranked.firstOrNull()
        prefs.edit().putString("catchworld_radar", arr.toString())
            .putInt("radar_cursor", if (markets.isEmpty()) 0 else (cursor + selected.size) % markets.size)
            .putInt("radar_market_count", markets.size).putLong("catchworld_updated", System.currentTimeMillis()).apply()
        if (best != null) {
            val x=best.snapshot; val s=best.signal
            prefs.edit().putString("catchworld_market",x.market).putString("catchworld_state",s.state.name).putInt("catchworld_score",s.score)
                .putString("catchworld_reason",s.reason.joinToString(" · ")).putString("catchworld_price",x.price.toString())
                .putString("catchworld_vr1h",x.volumeRatio1h.toString()).putString("catchworld_rsi",x.rsi14.toString()).putString("catchworld_ret1h",x.return1h.toString()).apply()
        }
        DaonWidget().updateAll(applicationContext)
        Result.success()
    } catch (_: Exception) { Result.retry() }

    private fun notifySignal(market: String, signal: CatchWorldSignal) {
        val nm = applicationContext.getSystemService(Context.NOTIFICATION_SERVICE) as NotificationManager
        val title = when (signal.state) { CatchWorldState.BLUE->"🔵 $market BLUE 후보"; CatchWorldState.PRE_BLUE->"🟣 $market PRE-BLUE"; CatchWorldState.EXIT_RISK->"🔴 $market 자금이탈 위험"; else->"$market ${signal.state.name}" }
        val text="기회점수 ${signal.score} · ${signal.reason.joinToString(" · ")}"
        nm.notify(market.hashCode() xor signal.state.hashCode(), NotificationCompat.Builder(applicationContext,"signals").setSmallIcon(android.R.drawable.ic_dialog_info).setContentTitle(title).setContentText(text).setStyle(NotificationCompat.BigTextStyle().bigText(text)).setAutoCancel(true).build())
    }
}
