package com.daon.futures

import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Modifier
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp

private val catchAssets=listOf("BTC","ETH","XRP","SOL","DOGE","ADA","AVAX","LINK","DOT","TRX")

@Composable
fun CoinBrowserScreen(){
    var selected by remember{mutableStateOf<String?>(null)}
    var query by remember{mutableStateOf("")}
    selected?.let { asset ->
        Column(Modifier.fillMaxSize()){
            TextButton(onClick={selected=null},modifier=Modifier.padding(horizontal=8.dp)){Text("‹ 코인 목록")}
            CoinDetailScreen(asset)
        }
        return
    }
    val filtered=catchAssets.filter{it.contains(query.trim(),ignoreCase=true)}
    LazyColumn(Modifier.fillMaxSize().padding(horizontal=14.dp),contentPadding=PaddingValues(vertical=14.dp),verticalArrangement=Arrangement.spacedBy(8.dp)){
        item{Text("코인",style=MaterialTheme.typography.headlineMedium,fontWeight=FontWeight.ExtraBold)}
        item{Text("UPBIT · BINANCE · BYBIT 실데이터 비교",style=MaterialTheme.typography.bodySmall)}
        item{OutlinedTextField(value=query,onValueChange={query=it},label={Text("코인 검색")},placeholder={Text("BTC, XRP, SOL…")},singleLine=true,modifier=Modifier.fillMaxWidth())}
        items(filtered){asset->Card(Modifier.fillMaxWidth().clickable{selected=asset}){Row(Modifier.fillMaxWidth().padding(16.dp),horizontalArrangement=Arrangement.SpaceBetween){Column{Text(asset,fontWeight=FontWeight.Bold);Text("KRW-$asset  ·  ${asset}USDT",style=MaterialTheme.typography.bodySmall)};Text("상세 ›")}}}
    }
}