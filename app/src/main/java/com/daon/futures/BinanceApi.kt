package com.daon.futures

import okhttp3.OkHttpClient
import okhttp3.Request
import org.json.JSONArray

object BinanceApi {
    private val client=OkHttpClient()
    private fun candles(symbol:String, interval:String, limit:Int=100):List<Candle>{
        val url="https://fapi.binance.com/fapi/v1/klines?symbol=$symbol&interval=$interval&limit=$limit"
        val req=Request.Builder().url(url).build()
        client.newCall(req).execute().use { res ->
            if(!res.isSuccessful) error("API ${res.code}")
            val a=JSONArray(res.body!!.string()); return (0 until a.length()).map{ val x=a.getJSONArray(it); Candle(x.getDouble(1),x.getDouble(2),x.getDouble(3),x.getDouble(4),x.getLong(6)) }
        }
    }
    fun analyze(symbol:String, sl:Double, tp:Double):Signal? = TradingEngine.signal(candles(symbol,"15m"),candles(symbol,"1h"),candles(symbol,"4h"),sl,tp)
    fun price(symbol:String):Double { val req=Request.Builder().url("https://fapi.binance.com/fapi/v1/ticker/price?symbol=$symbol").build(); client.newCall(req).execute().use{return org.json.JSONObject(it.body!!.string()).getDouble("price")} }
}
