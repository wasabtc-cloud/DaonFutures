package com.daon.futures.widget

import android.content.Context
import android.content.Intent
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import androidx.glance.GlanceModifier
import androidx.glance.action.clickable
import androidx.glance.appwidget.GlanceAppWidget
import androidx.glance.appwidget.GlanceAppWidgetReceiver
import androidx.glance.appwidget.action.actionStartActivity
import androidx.glance.appwidget.provideContent
import androidx.glance.background
import androidx.glance.color.ColorProvider
import androidx.glance.layout.*
import androidx.glance.text.FontWeight
import androidx.glance.text.Text
import androidx.glance.text.TextStyle
import androidx.glance.unit.ColorProvider as GlanceColorProvider
import com.daon.futures.MainActivity

class DaonWidget : GlanceAppWidget() {
    override suspend fun provideGlance(context: Context, id: androidx.glance.GlanceId) {
        provideContent {
            val p = context.getSharedPreferences("settings", 0)
            val sym = p.getString("last_symbol", p.getString("symbol", "BTCUSDT")) ?: "BTCUSDT"
            val price = p.getString("last_price", "-") ?: "-"
            val change = p.getString("last_change_pct", "-") ?: "-"
            val updated = p.getString("last_updated", "분석 대기") ?: "분석 대기"
            val tier = p.getString("last_alert_tier", "NORMAL") ?: "NORMAL"
            val exchange = p.getString("last_exchange", "UPBIT") ?: "UPBIT"
            val inflow = p.getString("last_inflow_strength", "-") ?: "-"
            val cross = p.getString("cross_exchange_state", "확인 중") ?: "확인 중"
            val goldValue = p.getString("widget_gold", "연결 준비") ?: "연결 준비"
            val fxValue = p.getString("widget_fx", "연결 준비") ?: "연결 준비"
            val depositValue = p.getString("widget_deposit", "연결 준비") ?: "연결 준비"
            val open = Intent(context, MainActivity::class.java)

            val white = ColorProvider(Color(0xFFF7F9FC), Color(0xFFF7F9FC))
            val muted = ColorProvider(Color(0xFF9AA5B4), Color(0xFF9AA5B4))
            val green = ColorProvider(Color(0xFF19D38A), Color(0xFF19D38A))
            val amber = ColorProvider(Color(0xFFFFB74D), Color(0xFFFFB74D))
            val gold = ColorProvider(Color(0xFFF3D36A), Color(0xFFF3D36A))
            val bg = ColorProvider(Color(0xFF0D1420), Color(0xFF0D1420))
            val accent = ColorProvider(Color(0xFF72A7FF), Color(0xFF72A7FF))
            val tierText = when (tier) { "SUPER" -> "S  강한 신호"; "ADDITIONAL" -> "✓✓  추가유입"; else -> "✓  자금유입" }
            val tierColor = when (tier) { "SUPER" -> gold; "ADDITIONAL" -> amber; else -> green }

            Column(GlanceModifier.fillMaxSize().background(bg).padding(14.dp).clickable(actionStartActivity(open))) {
                Row(GlanceModifier.fillMaxWidth()) {
                    Column(GlanceModifier.defaultWeight()) {
                        Text("CATCH WORLD", style = TextStyle(color = white, fontWeight = FontWeight.Bold, fontSize = 14.sp))
                        Text("오늘의 기회", style = TextStyle(color = muted, fontSize = 10.sp))
                    }
                    Text(updated, style = TextStyle(color = muted, fontSize = 9.sp))
                }
                Row(GlanceModifier.fillMaxWidth().padding(top = 10.dp)) {
                    Column(GlanceModifier.defaultWeight()) {
                        Text("$sym  ·  $exchange", style = TextStyle(color = white, fontWeight = FontWeight.Bold, fontSize = 13.sp))
                        Text(price, style = TextStyle(color = white, fontWeight = FontWeight.Bold, fontSize = 20.sp))
                        Text("$change%", style = TextStyle(color = green, fontWeight = FontWeight.Bold, fontSize = 12.sp))
                    }
                    Column(horizontalAlignment = Alignment.Horizontal.End) {
                        Text(tierText, style = TextStyle(color = tierColor, fontWeight = FontWeight.Bold, fontSize = 12.sp))
                        Text("자금유입 $inflow", style = TextStyle(color = muted, fontSize = 10.sp))
                        Text("3거래소 $cross", style = TextStyle(color = accent, fontSize = 10.sp))
                    }
                }
                Row(GlanceModifier.fillMaxWidth().padding(top = 12.dp)) {
                    MiniAsset("금", goldValue, gold, white, GlanceModifier.defaultWeight())
                    Spacer(GlanceModifier.width(6.dp))
                    MiniAsset("환율", fxValue, accent, white, GlanceModifier.defaultWeight())
                    Spacer(GlanceModifier.width(6.dp))
                    MiniAsset("예금", depositValue, green, white, GlanceModifier.defaultWeight())
                }
                Text("탭하여 캐치월드 열기", modifier = GlanceModifier.padding(top = 10.dp), style = TextStyle(color = muted, fontSize = 9.sp))
            }
        }
    }
}

@androidx.glance.GlanceComposable
@androidx.compose.runtime.Composable
private fun MiniAsset(title: String, value: String, accent: GlanceColorProvider, white: GlanceColorProvider, modifier: GlanceModifier) {
    val cardBg = ColorProvider(Color(0xFF151F2D), Color(0xFF151F2D))
    Column(modifier.background(cardBg).padding(8.dp)) {
        Text(title, style = TextStyle(color = accent, fontWeight = FontWeight.Bold, fontSize = 10.sp))
        Text(value, style = TextStyle(color = white, fontWeight = FontWeight.Bold, fontSize = 11.sp))
    }
}

class DaonWidgetReceiver : GlanceAppWidgetReceiver() {
    override val glanceAppWidget: GlanceAppWidget = DaonWidget()
}
