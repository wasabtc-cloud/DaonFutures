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
import java.util.Locale

class DaonWidget:GlanceAppWidget(){override suspend fun provideGlance(context:Context,id:androidx.glance.GlanceId){provideContent{
    val p=context.getSharedPreferences("settings",0);val sym=p.getString("last_symbol",p.getString("symbol","BTCUSDT"))?:"BTCUSDT";val side=p.getString("last_side","WAIT")?:"WAIT";val price=p.getString("last_price","-")?:"-";val sSl=p.getString("last_sl","-")?:"-";val sTp=p.getString("last_tp","-")?:"-";val rsi=p.getString("last_rsi","-")?:"-";val updated=p.getString("last_updated","앱에서 분석 필요")?:"앱에서 분석 필요";val setSl=String.format(Locale.KOREA,"%.1f%%",p.getFloat("sl",1f));val setTp=String.format(Locale.KOREA,"%.1f%%",p.getFloat("tp",1.5f));val lev=p.getInt("lev",3);val open=Intent(context,MainActivity::class.java)
    val white=ColorProvider(Color(0xFFF7F9FC),Color(0xFFF7F9FC));val muted=ColorProvider(Color(0xFF9AA5B4),Color(0xFF9AA5B4));val green=ColorProvider(Color(0xFF19D38A),Color(0xFF19D38A));val red=ColorProvider(Color(0xFFFF4D63),Color(0xFFFF4D63));val bg=ColorProvider(Color(0xFF0D1420),Color(0xFF0D1420));val accent=ColorProvider(Color(0xFF8B7CFF),Color(0xFF8B7CFF));val line=ColorProvider(Color(0xFF253044),Color(0xFF253044));val sideColor=when(side){"LONG"->green;"SHORT"->red;else->muted}
    Column(GlanceModifier.fillMaxSize().background(bg).padding(14.dp).clickable(actionStartActivity(open))){
        Row(GlanceModifier.fillMaxWidth()){Text("다온이 선물매매",style=TextStyle(color=white,fontWeight=FontWeight.Bold,fontSize=14.sp));Text("  v2.5",style=TextStyle(color=accent,fontWeight=FontWeight.Bold,fontSize=13.sp))}
        Row(GlanceModifier.fillMaxWidth().padding(top=7.dp)){Column(GlanceModifier.defaultWeight()){Text(sym,style=TextStyle(color=white,fontWeight=FontWeight.Bold,fontSize=14.sp));Text(price,modifier=GlanceModifier.padding(top=2.dp),style=TextStyle(color=white,fontWeight=FontWeight.Bold,fontSize=20.sp))};Column(horizontalAlignment=Alignment.Horizontal.End){Text(when(side){"LONG"->"▲ LONG";"SHORT"->"▼ SHORT";else->"● 대기"},style=TextStyle(color=sideColor,fontWeight=FontWeight.Bold,fontSize=14.sp));Text("One Candle",modifier=GlanceModifier.padding(top=2.dp),style=TextStyle(color=muted,fontSize=10.sp))}}
        Box(GlanceModifier.fillMaxWidth().height(1.dp).padding(top=7.dp).background(line)){}
        Row(GlanceModifier.fillMaxWidth().padding(top=8.dp)){Column(GlanceModifier.defaultWeight()){Text("RSI",style=TextStyle(color=muted,fontSize=10.sp));Text(rsi,style=TextStyle(color=accent,fontWeight=FontWeight.Bold,fontSize=12.sp))};Column(GlanceModifier.defaultWeight()){Text("손절",style=TextStyle(color=muted,fontSize=10.sp));Text(if(side=="WAIT")setSl else sSl,style=TextStyle(color=red,fontWeight=FontWeight.Bold,fontSize=12.sp))};Column(GlanceModifier.defaultWeight()){Text("목표",style=TextStyle(color=muted,fontSize=10.sp));Text(if(side=="WAIT")setTp else sTp,style=TextStyle(color=green,fontWeight=FontWeight.Bold,fontSize=12.sp))};Column(horizontalAlignment=Alignment.Horizontal.End){Text("레버리지",style=TextStyle(color=muted,fontSize=10.sp));Text("${lev}배",style=TextStyle(color=white,fontWeight=FontWeight.Bold,fontSize=12.sp))}}
        Text("4H/1H 추세 + 15M 진입 · $updated",modifier=GlanceModifier.padding(top=8.dp),style=TextStyle(color=muted,fontSize=9.sp))
    }
}}}
class DaonWidgetReceiver:GlanceAppWidgetReceiver(){override val glanceAppWidget:GlanceAppWidget=DaonWidget()}