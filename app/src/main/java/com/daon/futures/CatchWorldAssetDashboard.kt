package com.daon.futures

/** UI-ready model for CatchWorld's cross-asset home screen. */
data class CatchWorldAssetDashboard(
    val updatedAtMillis: Long,
    val opportunities: List<AssetOpportunity>,
    val strongest: AssetOpportunity?,
    val gold: List<AssetOpportunity>,
    val etfs: List<AssetOpportunity>,
    val deposits: List<AssetOpportunity>
)

object CatchWorldAssetDashboardBuilder {
    fun build(
        goldSnapshots: List<GoldSnapshot>,
        etfSnapshots: List<EtfSnapshot>,
        depositSnapshots: List<DepositSnapshot>,
        nowMillis: Long = System.currentTimeMillis()
    ): CatchWorldAssetDashboard {
        val gold = goldSnapshots.map(AssetOpportunityEngine::gold)
        val etfs = etfSnapshots.map(AssetOpportunityEngine::etf)
        val deposits = AssetOpportunityEngine.deposits(depositSnapshots)
        val ranked = AssetOpportunityEngine.rankAll(gold + etfs + deposits)
        return CatchWorldAssetDashboard(
            updatedAtMillis = nowMillis,
            opportunities = ranked,
            strongest = ranked.firstOrNull(),
            gold = gold,
            etfs = etfs,
            deposits = deposits
        )
    }
}

/**
 * Provider boundary for real market/bank data. Implementations can use
 * different public providers without coupling network code to the UI.
 */
interface CatchWorldAssetDataProvider {
    suspend fun gold(): List<GoldSnapshot>
    suspend fun etfs(): List<EtfSnapshot>
    suspend fun deposits(): List<DepositSnapshot>
}

class CatchWorldAssetRepository(
    private val provider: CatchWorldAssetDataProvider
) {
    suspend fun refresh(): CatchWorldAssetDashboard =
        CatchWorldAssetDashboardBuilder.build(
            goldSnapshots = provider.gold(),
            etfSnapshots = provider.etfs(),
            depositSnapshots = provider.deposits()
        )
}
