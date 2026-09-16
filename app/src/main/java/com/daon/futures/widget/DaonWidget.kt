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
import com.daon.futures.MainActivity

class DaonWidget:GlanceAppWidget(){override suspend fun provideGlance(context:Context,id:androidx.glance.GlanceId){provideContent{
    val p=context.getSharedPreferences("settings",0);val sym=p.getString("last_symbol",p.getString("symbol","BTCUSDT"))?:"BTCUSDT";val side=p.getString("last_side","WAIT")?:"WAIT";val price=p.getString("last_price","-")?:"-";val rsi=p.getString("last_rsi","-")?:"-";val updated=p.getString("last_updated","분석 대기")?:"분석 대기";val tier=p.getString("last_alert_tier","NORMAL")?:"NORMAL";val open=Intent(context,MainActivity::class.java)
    val white=ColorProvider(Color(0xFFF7F9FC),Color(0xFFF7F9FC));val muted=ColorProvider(Color(0xFF9AA5B4),Color(0xFF9AA5B4));val green=ColorProvider(Color(0xFF19D38A),Color(0xFF19D38A));val amber=ColorProvider(Color(0xFFFFB74D),Color(0xFFFFB74D));val gold=ColorProvider(Color(0xFFF3D36A),Color(0xFFF3D36A));val bg=ColorProvider(Color(0xFF0D1420),Color(0xFF0D1420));val accent=ColorProvider(Color(0xFF8B7CFF),Color(0xFF8B7CFF));val tierText=when(tier){"SUPER"->"S SUPER SIGNAL";"ADDITIONAL"->"✓✓ 추가유입";else->"✓ 자금유입"};val tierColor=when(tier){"SUPER"->gold;"ADDITIONAL"->amber;else->green}
    Column(GlanceModifier.fillMaxSize().background(bg).padding(14.dp).clickable(actionStartActivity(open))){
        Row(GlanceModifier.fillMaxWidth()){Text("CATCH WORLD",style=TextStyle(color=white,fontWeight=FontWeight.Bold,fontSize=14.sp));Text("  v2.6",style=TextStyle(color=accent,fontWeight=FontWeight.Bold,fontSize=10.sp))}
        Text(tierText,modifier=GlanceModifier.padding(top=6.dp),style=TextStyle(color=tierColor,fontWeight=FontWeight.Bold,fontSize=12.sp))
        Row(GlanceModifier.fillMaxWidth().padding(top=5.dp)){Column(GlanceModifier.defaultWeight()){Text(sym,style=TextStyle(color=white,fontWeight=FontWeight.Bold,fontSize=14.sp));Text(price,style=TextStyle(color=white,fontWeight=FontWeight.Bold,fontSize=20.sp))};Column(horizontalAlignment=Alignment.Horizontal.End){Text(if(side=="WAIT")"● 대기" else if(side=="LONG")"▲ LONG" else "▼ SHORT",style=TextStyle(color=if(side=="WAIT")muted else green,fontWeight=FontWeight.Bold,fontSize=13.sp));Text("RSI $rsi",style=TextStyle(color=muted,fontSize=10.sp))}}
        Text("신호시간 $updated",modifier=GlanceModifier.padding(top=8.dp),style=TextStyle(color=muted,fontSize=10.sp))
        Text("탭하여 캐치월드 열기",modifier=GlanceModifier.padding(top=5.dp),style=TextStyle(color=accent,fontWeight=FontWeight.Bold,fontSize=10.sp))
    }
}}}
class DaonWidgetReceiver:GlanceAppWidgetReceiver(){override val glanceAppWidget:GlanceAppWidget=DaonWidget()}
