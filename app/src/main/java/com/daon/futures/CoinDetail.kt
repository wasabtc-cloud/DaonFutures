package com.daon.futures

import androidx.compose.foundation.layout.*
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Modifier
import androidx.compose.ui.unit.dp
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext

@Composable
fun CoinDetailScreen(symbol:String="BTCUSDT") {
    var exchange by remember { mutableStateOf("BINANCE") }
    var interval by remember { mutableStateOf("15분") }
    var candles by remember { mutableStateOf<List<Candle>>(emptyList()) }
    var quote by remember { mutableStateOf<GlobalExchangeApi.Quote?>(null) }
    var loading by remember { mutableStateOf(true) }
    val intervalCode = when(interval){"5분"->"5m";"1시간"->"1h";"4시간"->"4h";else->"15m"}
    val bybitInterval = when(interval){"5분"->"5";"1시간"->"60";"4시간"->"240";else->"15"}

    LaunchedEffect(exchange,interval,symbol){
        loading=true
        val result=withContext(Dispatchers.IO){
            if(exchange=="BYBIT") Pair(GlobalExchangeApi.bybitQuote(symbol),GlobalExchangeApi.bybitCandles(symbol,bybitInterval))
            else Pair(GlobalExchangeApi.binanceQuote(symbol),GlobalExchangeApi.binanceCandles(symbol,intervalCode))
        }
        quote=result.first
        candles=result.second.map { Candle(open=it.open, high=it.high, low=it.low, close=it.close, closeTime=it.time) }
        loading=false
    }

    LazyColumn(Modifier.fillMaxSize().padding(horizontal=14.dp),contentPadding=PaddingValues(vertical=14.dp),verticalArrangement=Arrangement.spacedBy(10.dp)){
        item { Text(symbol, style=MaterialTheme.typography.headlineMedium) }
        item { Row(horizontalArrangement=Arrangement.spacedBy(6.dp)){ listOf("BINANCE","BYBIT").forEach{ FilterChip(selected=exchange==it,onClick={exchange=it},label={Text(it)}) } } }
        item { Row(horizontalArrangement=Arrangement.spacedBy(6.dp)){ listOf("5분","15분","1시간","4시간").forEach{ FilterChip(selected=interval==it,onClick={interval=it},label={Text(it)}) } } }
        item { quote?.let { Text("${it.exchange}  ${it.price}  24H ${"%.2f".format(it.changePct)}%") } ?: Text(if(loading) "실제 시장 데이터를 불러오는 중…" else "데이터를 불러오지 못했습니다.") }
        item { if(loading) LinearProgressIndicator(Modifier.fillMaxWidth()) else MarketChartCard(symbol,interval,candles,Modifier.fillMaxWidth()) }
        item { Text("✓ / ✓✓ / S 표시는 현재 연구·검증 중인 차트 규칙입니다. 자동주문은 실행하지 않습니다.",style=MaterialTheme.typography.bodySmall) }
    }
}