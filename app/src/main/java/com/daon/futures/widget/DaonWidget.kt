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

class DaonWidget:GlanceAppWidget(){
    override suspend fun provideGlance(context:Context,id:androidx.glance.GlanceId){
        provideContent{
            val p=context.getSharedPreferences("settings",0)
            val sym=p.getString("last_symbol",p.getString("symbol","BTCUSDT"))?:"BTCUSDT"
            val side=p.getString("last_side","WAIT")?:"WAIT"
            val price=p.getString("last_price","-")?:"-"
            val sl=p.getString("last_sl","-")?:"-"
            val tp=p.getString("last_tp","-")?:"-"
            val rsi=p.getString("last_rsi","-")?:"-"
            val updated=p.getString("last_updated","앱에서 분석 필요")?:"앱에서 분석 필요"
            val openApp=Intent(context,MainActivity::class.java)
            Column(
                GlanceModifier.fillMaxSize()
                    .background(ColorProvider(Color(0xFF171A21), Color(0xFF171A21)))
                    .padding(14.dp)
                    .clickable(actionStartActivity(openApp)),
                verticalAlignment=Alignment.Vertical.CenterVertically
            ){
                Text("다온이 선물매매",style=TextStyle(fontWeight=FontWeight.Bold,fontSize=15.sp))
                Text("$sym  ${when(side){"LONG"->"🟢 LONG";"SHORT"->"🔴 SHORT";else->"⚪ 대기"}}",modifier=GlanceModifier.padding(top=4.dp))
                Text("진입 $price",modifier=GlanceModifier.padding(top=5.dp))
                Row(modifier=GlanceModifier.padding(top=2.dp)){
                    Text("SL $sl",modifier=GlanceModifier.padding(end=9.dp))
                    Text("TP $tp")
                }
                Text("RSI $rsi · $updated",modifier=GlanceModifier.padding(top=5.dp),style=TextStyle(fontSize=10.sp))
            }
        }
    }
}

class DaonWidgetReceiver:GlanceAppWidgetReceiver(){
    override val glanceAppWidget:GlanceAppWidget=DaonWidget()
}
