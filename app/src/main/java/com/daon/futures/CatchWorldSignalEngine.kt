package com.daon.futures

import kotlin.math.abs

data class CatchWorldSnapshot(
    val market: String,
    val price: Double,
    val ema20: Double,
    val ema60: Double,
    val rsi14: Double,
    val bbWidth: Double,
    val volumeRatio1h: Double,
    val return1h: Double,
    val relativeStrength24h: Double = 0.0,
    val priorWhaleSeen: Boolean = false
)

enum class CatchWorldState { WATCH, WHALE, HOLDING, PRE_BLUE, BLUE, EXIT_RISK }

data class CatchWorldSignal(
    val state: CatchWorldState,
    val score: Int,
    val reason: List<String>
)

data class CatchWorldStrategyConfig(
    val whaleVr: Double = 8.0,
    val minRsi: Double = 45.0,
    val maxBbWidth: Double = 0.05,
    val emaTolerance: Double = 0.995,
    val exitDrop1h: Double = -0.03
)

/**
 * Pure strategy layer: UI/network/storage are deliberately kept outside so
 * thresholds and rules can be replaced after each backtest without rebuilding
 * the rest of CatchWorld.
 *
 * BLUE is a research candidate signal, not an automatic order instruction.
 */
object CatchWorldSignalEngine {
    fun evaluate(
        x: CatchWorldSnapshot,
        config: CatchWorldStrategyConfig = CatchWorldStrategyConfig()
    ): CatchWorldSignal {
        val reasons = mutableListOf<String>()
        var score = 0

        val whale = x.volumeRatio1h >= config.whaleVr
        val trend = x.price >= x.ema20 && x.ema20 >= x.ema60 * config.emaTolerance
        val momentum = x.rsi14 >= config.minRsi
        val compressed = x.bbWidth <= config.maxBbWidth
        val holding = x.priorWhaleSeen && x.price >= x.ema60 * 0.98
        val exitRisk = x.priorWhaleSeen && x.return1h <= config.exitDrop1h && x.volumeRatio1h >= 3.0

        if (whale) { score += 30; reasons += "1시간 거래대금 비율 ${fmt(x.volumeRatio1h)}x" }
        if (holding) { score += 20; reasons += "이전 고래 흔적 이후 가격 방어" }
        if (trend) { score += 20; reasons += "EMA20/60 추세 조건" }
        if (momentum) { score += 15; reasons += "RSI ${fmt(x.rsi14)}" }
        if (compressed) { score += 15; reasons += "변동성 압축" }
        if (x.relativeStrength24h > 0) reasons += "BTC 대비 상대강도 우위"

        val state = when {
            exitRisk -> CatchWorldState.EXIT_RISK
            whale && holding && trend && momentum && compressed -> CatchWorldState.BLUE
            holding && trend && momentum && compressed -> CatchWorldState.PRE_BLUE
            holding -> CatchWorldState.HOLDING
            whale -> CatchWorldState.WHALE
            else -> CatchWorldState.WATCH
        }
        return CatchWorldSignal(state, score.coerceIn(0, 100), reasons)
    }

    private fun fmt(v: Double) = String.format(java.util.Locale.US, "%.2f", v)
}
