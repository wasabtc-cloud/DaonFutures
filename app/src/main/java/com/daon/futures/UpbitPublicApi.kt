package com.daon.futures

import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext
import org.json.JSONArray
import java.net.HttpURLConnection
import java.net.URL

data class UpbitCandle(
    val timestamp: Long,
    val open: Double,
    val high: Double,
    val low: Double,
    val close: Double,
    val tradePrice: Double,
    val tradeVolume: Double
)

/** Public market-data client. No API key and no order endpoint. */
object UpbitPublicApi {
    private fun get(urlText: String): String {
        val conn = (URL(urlText).openConnection() as HttpURLConnection).apply {
            requestMethod = "GET"
            connectTimeout = 8000
            readTimeout = 8000
            setRequestProperty("Accept", "application/json")
        }
        return try {
            if (conn.responseCode !in 200..299) error("Upbit HTTP ${conn.responseCode}")
            conn.inputStream.bufferedReader().use { it.readText() }
        } finally { conn.disconnect() }
    }

    suspend fun krwMarkets(): List<String> = withContext(Dispatchers.IO) {
        val arr = JSONArray(get("https://api.upbit.com/v1/market/all?is_details=false"))
        buildList {
            for (i in 0 until arr.length()) {
                val market = arr.getJSONObject(i).getString("market")
                if (market.startsWith("KRW-")) add(market)
            }
        }.sorted()
    }

    suspend fun minuteCandles(market: String, unit: Int = 15, count: Int = 200): List<UpbitCandle> =
        withContext(Dispatchers.IO) {
            require(unit in setOf(1, 3, 5, 10, 15, 30, 60, 240))
            val safeCount = count.coerceIn(1, 200)
            val arr = JSONArray(get("https://api.upbit.com/v1/candles/minutes/$unit?market=${market.uppercase()}&count=$safeCount"))
            buildList {
                for (i in 0 until arr.length()) {
                    val x = arr.getJSONObject(i)
                    add(UpbitCandle(
                        timestamp = x.getLong("timestamp"),
                        open = x.getDouble("opening_price"), high = x.getDouble("high_price"), low = x.getDouble("low_price"),
                        close = x.getDouble("trade_price"), tradePrice = x.getDouble("candle_acc_trade_price"),
                        tradeVolume = x.getDouble("candle_acc_trade_volume")
                    ))
                }
            }.sortedBy { it.timestamp }
        }
}
