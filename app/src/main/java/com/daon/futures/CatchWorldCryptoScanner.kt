package com.daon.futures

/** Connects live Upbit candles -> indicators -> CatchWorld state engine. */
data class CatchWorldScanResult(
    val snapshot: CatchWorldSnapshot,
    val signal: CatchWorldSignal
)

class CatchWorldCryptoScanner {
    suspend fun scan(
        market: String,
        priorWhaleSeen: Boolean = false
    ): CatchWorldScanResult {
        val candles = UpbitPublicApi.minuteCandles(market = market, unit = 15, count = 200)
        val snapshot = requireNotNull(
            CatchWorldIndicators.snapshot(
                market = market,
                candles = candles,
                priorWhaleSeen = priorWhaleSeen
            )
        ) { "Not enough Upbit candles for $market" }
        return CatchWorldScanResult(snapshot, CatchWorldSignalEngine.evaluate(snapshot))
    }
}
