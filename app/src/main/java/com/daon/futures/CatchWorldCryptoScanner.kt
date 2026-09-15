package com.daon.futures

/** Connects live Upbit candles -> indicators -> CatchWorld state engine. */
class CatchWorldCryptoScanner(
    private val api: UpbitPublicApi = UpbitPublicApi()
) {
    suspend fun scan(
        market: String,
        priorWhaleSeen: Boolean = false
    ): CatchWorldSignal {
        val candles = api.minuteCandles(market = market, unit = 15, count = 200)
        val snapshot = CatchWorldIndicators.snapshot(
            market = market,
            candles = candles,
            priorWhaleSeen = priorWhaleSeen
        )
        return CatchWorldSignalEngine.evaluate(snapshot)
    }
}
