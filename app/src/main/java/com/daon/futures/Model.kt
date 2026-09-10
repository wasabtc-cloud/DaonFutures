package com.daon.futures

data class Candle(val open: Double, val high: Double, val low: Double, val close: Double, val closeTime: Long)
data class Signal(val side: String, val price: Double, val sl: Double, val tp: Double, val rsi: Double, val reason: String, val candleTime: Long = System.currentTimeMillis())
data class SignalRecord(val symbol: String, val side: String, val price: Double, val sl: Double, val tp: Double, val rsi: Double, val timestamp: Long)
