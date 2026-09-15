package com.daon.futures

import androidx.compose.foundation.layout.*
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp

@Composable
fun AlertSettingsCard() {
    val context = LocalContext.current
    var normal by remember { mutableStateOf(AppStore.alertEnabled(context, AppStore.ALERT_NORMAL)) }
    var additional by remember { mutableStateOf(AppStore.alertEnabled(context, AppStore.ALERT_ADDITIONAL)) }
    var superSignal by remember { mutableStateOf(AppStore.alertEnabled(context, AppStore.ALERT_SUPER)) }

    fun save() = AppStore.saveAlertSettings(context, normal, additional, superSignal)

    Card(shape = RoundedCornerShape(18.dp)) {
        Column(Modifier.fillMaxWidth().padding(16.dp), verticalArrangement = Arrangement.spacedBy(4.dp)) {
            Text("자금유입 알림 설정", fontSize = 18.sp, fontWeight = FontWeight.ExtraBold)
            Text("신호 단계별로 알림을 따로 켜고 끌 수 있습니다.", style = MaterialTheme.typography.bodySmall)
            AlertToggleRow("일반 자금유입", "초기 유입 감지", normal) { normal = it; save() }
            HorizontalDivider()
            AlertToggleRow("추가 자금유입", "유입이 다시 강해질 때", additional) { additional = it; save() }
            HorizontalDivider()
            AlertToggleRow("SUPER SIGNAL", "가장 강한 신호", superSignal) { superSignal = it; save() }
        }
    }
}

@Composable
private fun AlertToggleRow(title:String, subtitle:String, checked:Boolean, onChecked:(Boolean)->Unit) {
    Row(Modifier.fillMaxWidth().padding(vertical = 8.dp), horizontalArrangement = Arrangement.SpaceBetween) {
        Column(Modifier.weight(1f)) {
            Text(title, fontWeight = FontWeight.Bold)
            Text(subtitle, style = MaterialTheme.typography.bodySmall)
        }
        Switch(checked = checked, onCheckedChange = onChecked)
    }
}
