package com.daon.futures

import androidx.compose.foundation.layout.*
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Modifier
import androidx.compose.ui.unit.dp
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext

private fun globalSymbol(asset:String)=asset.uppercase()+"USDT"
private fun upbitMarket(asset:String)="KRW-"+asset.uppercase()
@Composable fun CoinDetailScreen(asset:String="BTC"){
 var exchange by remember{mutableStateOf("UPBIT")};var interval by remember{mutableStateOf("15분")};var candles by remember{mutableStateOf<List<Candle>>(emptyList())};var quote by remember{mutableStateOf<GlobalExchangeApi.Quote?>(null)};var loading by remember{mutableStateOf(true)}
 val global=globalSymbol(asset);val upbit=upbitMarket(asset);val intervalCode=when(interval){"5분"->"5m";"1시간"->"1h";"4시간"->"4h";else->"15m"};val bybitInterval=when(interval){"5분"->"5";"1시간"->"60";"4시간"->"240";else->"15"};val upbitUnit=when(interval){"5분"->5;"1시간"->60;"4시간"->240;else->15}
 LaunchedEffect(exchange,interval,asset){loading=true;val result=withContext(Dispatchers.IO){when(exchange){"UPBIT"->Pair(GlobalExchangeApi.upbitQuote(upbit),GlobalExchangeApi.upbitCandles(upbit,upbitUnit));"BYBIT"->Pair(GlobalExchangeApi.bybitQuote(global),GlobalExchangeApi.bybitCandles(global,bybitInterval));else->Pair(GlobalExchangeApi.binanceQuote(global),GlobalExchangeApi.binanceCandles(global,intervalCode))}};quote=result.first;candles=result.second.map{Candle(open=it.open,high=it.high,low=it.low,close=it.close,closeTime=it.time)};loading=false}
 LazyColumn(Modifier.fillMaxSize().padding(horizontal=14.dp),contentPadding=PaddingValues(vertical=14.dp),verticalArrangement=Arrangement.spacedBy(10.dp)){item{Text(asset.uppercase(),style=MaterialTheme.typography.headlineMedium)};item{Row(horizontalArrangement=Arrangement.spacedBy(6.dp)){listOf("UPBIT","BINANCE","BYBIT").forEach{FilterChip(selected=exchange==it,onClick={exchange=it},label={Text(it)})}}};item{Row(horizontalArrangement=Arrangement.spacedBy(6.dp)){listOf("5분","15분","1시간","4시간").forEach{FilterChip(selected=interval==it,onClick={interval=it},label={Text(it)})}}};item{quote?.let{Text("${it.exchange}  ${it.price}  24H ${"%.2f".format(it.changePct)}%") }?:Text(if(loading)"실제 시장 데이터를 불러오는 중…" else "데이터를 불러오지 못했습니다.")};item{if(loading)LinearProgressIndicator(Modifier.fillMaxWidth()) else MarketChartCard(asset.uppercase(),interval,candles,Modifier.fillMaxWidth(),exchange)};item{Text("✓ / ✓✓ / S는 연구·검증 중인 신호이며 자동주문은 실행하지 않습니다.",style=MaterialTheme.typography.bodySmall)}}
}