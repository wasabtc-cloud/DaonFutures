package com.daon.futures

// Correct adapter for GlobalExchangeApi candles to the app chart Candle model.
fun GlobalExchangeApi.Candle.toChartCandle(): Candle = Candle(
    open = open,
    high = high,
    low = low,
    close = close,
    closeTime = time
)
