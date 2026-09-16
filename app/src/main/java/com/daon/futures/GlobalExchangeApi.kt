package com.daon.futures

import okhttp3.OkHttpClient
import okhttp3.Request
import org.json.JSONObject
import org.json.JSONArray

object GlobalExchangeApi {
    private val http = OkHttpClient()
    data class Quote(val exchange:String,val symbol:String,val price:Double,val changePct:Double,val volume24h:Double)
    data class Candle(val time:Long,val open:Double,val high:Double,val low:Double,val close:Double,val volume:Double)

    private fun body(url:String):String = http.newCall(Request.Builder().url(url).build()).execute().use { r ->
        if(!r.isSuccessful) error("HTTP ${r.code}")
        r.body?.string() ?: error("empty")
    }

    fun upbitQuote(market:String="KRW-BTC"): Quote? = runCatching {
        val j=JSONArray(body("https://api.upbit.com/v1/ticker?markets=$market")).getJSONObject(0)
        Quote("UPBIT",market,j.getDouble("trade_price"),j.getDouble("signed_change_rate")*100.0,j.getDouble("acc_trade_price_24h"))
    }.getOrNull()

    fun upbitCandles(market:String="KRW-BTC", unit:Int=15, limit:Int=200):List<Candle> = runCatching {
        val a=JSONArray(body("https://api.upbit.com/v1/candles/minutes/$unit?market=$market&count=$limit"))
        (0 until a.length()).map { i -> val j=a.getJSONObject(i); Candle(j.getLong("timestamp"),j.getDouble("opening_price"),j.getDouble("high_price"),j.getDouble("low_price"),j.getDouble("trade_price"),j.getDouble("candle_acc_trade_volume")) }.sortedBy{it.time}
    }.getOrDefault(emptyList())

    fun binanceQuote(symbol:String="BTCUSDT"): Quote? = runCatching {
        val j=JSONObject(body("https://api.binance.com/api/v3/ticker/24hr?symbol=$symbol")); Quote("BINANCE",symbol,j.getString("lastPrice").toDouble(),j.getString("priceChangePercent").toDouble(),j.getString("quoteVolume").toDouble())
    }.getOrNull()

    fun bybitQuote(symbol:String="BTCUSDT"): Quote? = runCatching {
        val j=JSONObject(body("https://api.bybit.com/v5/market/tickers?category=spot&symbol=$symbol")).getJSONObject("result").getJSONArray("list").getJSONObject(0)
        Quote("BYBIT",symbol,j.getString("lastPrice").toDouble(),j.getString("price24hPcnt").toDouble()*100.0,j.getString("turnover24h").toDouble())
    }.getOrNull()

    fun binanceCandles(symbol:String="BTCUSDT", interval:String="15m", limit:Int=200):List<Candle> = runCatching {
        val a=JSONArray(body("https://api.binance.com/api/v3/klines?symbol=$symbol&interval=$interval&limit=$limit")); (0 until a.length()).map{i->val x=a.getJSONArray(i);Candle(x.getLong(0),x.getString(1).toDouble(),x.getString(2).toDouble(),x.getString(3).toDouble(),x.getString(4).toDouble(),x.getString(5).toDouble())}
    }.getOrDefault(emptyList())

    fun bybitCandles(symbol:String="BTCUSDT", interval:String="15", limit:Int=200):List<Candle> = runCatching {
        val a=JSONObject(body("https://api.bybit.com/v5/market/kline?category=spot&symbol=$symbol&interval=$interval&limit=$limit")).getJSONObject("result").getJSONArray("list");(0 until a.length()).map{i->val x=a.getJSONArray(i);Candle(x.getString(0).toLong(),x.getString(1).toDouble(),x.getString(2).toDouble(),x.getString(3).toDouble(),x.getString(4).toDouble(),x.getString(5).toDouble())}.sortedBy{it.time}
    }.getOrDefault(emptyList())
}