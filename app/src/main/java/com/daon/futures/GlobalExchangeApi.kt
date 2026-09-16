package com.daon.futures

import okhttp3.OkHttpClient
import okhttp3.Request
import org.json.JSONObject
import org.json.JSONArray

object GlobalExchangeApi {
    private val http = OkHttpClient()
    data class Quote(val exchange:String,val symbol:String,val price:Double,val changePct:Double,val volume24h:Double)
    data class Candle(val time:Long,val open:Double,val high:Double,val low:Double,val close:Double,val volume:Double)

    fun binanceQuote(symbol:String="BTCUSDT"): Quote? = runCatching {
        val body=http.newCall(Request.Builder().url("https://api.binance.com/api/v3/ticker/24hr?symbol=$symbol").build()).execute().use{it.body?.string()?:error("empty")}
        val j=JSONObject(body); Quote("BINANCE",symbol,j.getString("lastPrice").toDouble(),j.getString("priceChangePercent").toDouble(),j.getString("quoteVolume").toDouble())
    }.getOrNull()

    fun bybitQuote(symbol:String="BTCUSDT"): Quote? = runCatching {
        val body=http.newCall(Request.Builder().url("https://api.bybit.com/v5/market/tickers?category=spot&symbol=$symbol").build()).execute().use{it.body?.string()?:error("empty")}
        val j=JSONObject(body).getJSONObject("result").getJSONArray("list").getJSONObject(0)
        Quote("BYBIT",symbol,j.getString("lastPrice").toDouble(),j.getString("price24hPcnt").toDouble()*100.0,j.getString("turnover24h").toDouble())
    }.getOrNull()

    fun binanceCandles(symbol:String="BTCUSDT", interval:String="15m", limit:Int=200):List<Candle> = runCatching {
        val body=http.newCall(Request.Builder().url("https://api.binance.com/api/v3/klines?symbol=$symbol&interval=$interval&limit=$limit").build()).execute().use{it.body?.string()?:error("empty")}
        val a=JSONArray(body); (0 until a.length()).map{i->val x=a.getJSONArray(i);Candle(x.getLong(0),x.getString(1).toDouble(),x.getString(2).toDouble(),x.getString(3).toDouble(),x.getString(4).toDouble(),x.getString(5).toDouble())}
    }.getOrDefault(emptyList())

    fun bybitCandles(symbol:String="BTCUSDT", interval:String="15", limit:Int=200):List<Candle> = runCatching {
        val body=http.newCall(Request.Builder().url("https://api.bybit.com/v5/market/kline?category=spot&symbol=$symbol&interval=$interval&limit=$limit").build()).execute().use{it.body?.string()?:error("empty")}
        val a=JSONObject(body).getJSONObject("result").getJSONArray("list");(0 until a.length()).map{i->val x=a.getJSONArray(i);Candle(x.getString(0).toLong(),x.getString(1).toDouble(),x.getString(2).toDouble(),x.getString(3).toDouble(),x.getString(4).toDouble(),x.getString(5).toDouble())}.sortedBy{it.time}
    }.getOrDefault(emptyList())
}