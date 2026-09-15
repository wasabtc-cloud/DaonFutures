package com.daon.futures

enum class AssetClass { CRYPTO, GOLD, ETF, DEPOSIT }
enum class OpportunityState { STRONG, WATCH, NEUTRAL, DEFENSIVE }

data class AssetOpportunity(
    val assetClass: AssetClass,
    val symbol: String,
    val name: String,
    val state: OpportunityState,
    val score: Int,
    val headline: String,
    val details: List<String> = emptyList()
)

data class GoldSnapshot(
    val name: String,
    val price: Double,
    val change1d: Double,
    val change20d: Double,
    val aboveEma20: Boolean,
    val aboveEma60: Boolean
)

data class EtfSnapshot(
    val symbol: String,
    val name: String,
    val change1d: Double,
    val change20d: Double,
    val aboveEma20: Boolean,
    val aboveEma60: Boolean,
    val relativeStrength20d: Double = 0.0
)

data class DepositSnapshot(
    val bank: String,
    val product: String,
    val annualRate: Double,
    val months: Int,
    val maxRate: Double? = null
)

/**
 * Cross-asset scoring layer. Data providers are deliberately separated so
 * gold/ETF/deposit sources can be replaced without changing the UI.
 */
object AssetOpportunityEngine {
    fun gold(x: GoldSnapshot): AssetOpportunity {
        var score = 40
        if (x.aboveEma20) score += 20
        if (x.aboveEma60) score += 15
        if (x.change20d > 0) score += 15
        if (x.change1d > 0) score += 10
        score = score.coerceIn(0, 100)
        val state = when {
            score >= 80 -> OpportunityState.STRONG
            score >= 60 -> OpportunityState.WATCH
            score >= 40 -> OpportunityState.NEUTRAL
            else -> OpportunityState.DEFENSIVE
        }
        return AssetOpportunity(AssetClass.GOLD, "GOLD", x.name, state, score,
            if (score >= 60) "금 추세 관심" else "금 추세 관찰",
            listOf("20일 ${pct(x.change20d)}", "1일 ${pct(x.change1d)}"))
    }

    fun etf(x: EtfSnapshot): AssetOpportunity {
        var score = 35
        if (x.aboveEma20) score += 20
        if (x.aboveEma60) score += 15
        if (x.change20d > 0) score += 15
        if (x.relativeStrength20d > 0) score += 15
        score = score.coerceIn(0, 100)
        val state = when {
            score >= 80 -> OpportunityState.STRONG
            score >= 60 -> OpportunityState.WATCH
            score >= 40 -> OpportunityState.NEUTRAL
            else -> OpportunityState.DEFENSIVE
        }
        return AssetOpportunity(AssetClass.ETF, x.symbol, x.name, state, score,
            if (score >= 60) "ETF 상대강도 관심" else "ETF 관찰",
            listOf("20일 ${pct(x.change20d)}", "상대강도 ${pct(x.relativeStrength20d)}"))
    }

    fun deposits(items: List<DepositSnapshot>): List<AssetOpportunity> {
        if (items.isEmpty()) return emptyList()
        val best = items.maxOf { it.maxRate ?: it.annualRate }
        return items.sortedByDescending { it.maxRate ?: it.annualRate }.map { x ->
            val rate = x.maxRate ?: x.annualRate
            val score = if (best <= 0) 0 else (rate / best * 100).toInt().coerceIn(0, 100)
            AssetOpportunity(
                AssetClass.DEPOSIT,
                x.bank,
                x.product,
                if (score >= 95) OpportunityState.STRONG else OpportunityState.WATCH,
                score,
                "연 ${"%.2f".format(rate)}% · ${x.months}개월",
                listOf(x.bank)
            )
        }
    }

    fun rankAll(items: List<AssetOpportunity>): List<AssetOpportunity> =
        items.sortedByDescending { it.score }

    private fun pct(v: Double) = "%+.1f%%".format(v * 100.0)
}
