package com.daon.futures

import android.content.Intent
import android.net.Uri
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import java.text.SimpleDateFormat
import java.util.Date
import java.util.Locale

@Composable
fun TradeJournalCard() {
    val context = LocalContext.current
    var memo by remember { mutableStateOf("") }
    var records by remember { mutableStateOf(AppStore.journal(context)) }
    Card(shape = RoundedCornerShape(18.dp)) {
        Column(Modifier.fillMaxWidth().padding(16.dp), verticalArrangement = Arrangement.spacedBy(8.dp)) {
            Text("메모 · 매매일지", fontWeight = FontWeight.ExtraBold)
            OutlinedTextField(value = memo, onValueChange = { memo = it }, modifier = Modifier.fillMaxWidth(), label = { Text("지금 보는 신호/생각 기록") })
            Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                Button(onClick = {
                    if (memo.isNotBlank()) {
                        AppStore.addJournal(context, memo.trim())
                        memo = ""
                        records = AppStore.journal(context)
                    }
                }) { Text("메모 저장") }
                OutlinedButton(onClick = {
                    val app = Intent(Intent.ACTION_VIEW, Uri.parse("upbit://"))
                    val web = Intent(Intent.ACTION_VIEW, Uri.parse("https://upbit.com/exchange?code=CRIX.UPBIT.KRW-BTC"))
                    runCatching { context.startActivity(app) }.getOrElse { context.startActivity(web) }
                }) { Text("업비트 바로가기") }
            }
            records.take(5).forEach { r ->
                HorizontalDivider()
                Text(SimpleDateFormat("MM/dd HH:mm", Locale.KOREA).format(Date(r.time)), style = MaterialTheme.typography.labelSmall)
                Text(r.memo, style = MaterialTheme.typography.bodyMedium)
            }
        }
    }
}
