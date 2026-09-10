package com.daon.futures

import androidx.compose.foundation.Canvas
import androidx.compose.foundation.background
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.Card
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.ui.Modifier
import androidx.compose.ui.geometry.Offset
import androidx.compose.ui.geometry.Size
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.Path
import androidx.compose.ui.graphics.drawscope.Stroke
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import java.util.Locale
import kotlin.math.abs
import kotlin.math.max
import kotlin.math.min

fun emaSeries(values: List<Double>, period: Int): List<Double> {
    if (values.isEmpty()) return emptyList()
    val k = 2.0 / (period + 1.0)
    val out = MutableList(values.size) { 0.0 }
    var ema = values.first(); out[0] = ema
    for (i in 1 until values.size) { ema = values[i] * k + ema * (1.0-k); out[i]=ema }
    return out
}

fun rsiValue(values: List<Double>, period: Int = 14): Double {
    if (values.size <= period) return 50.0
    var gains=0.0; var losses=0.0
    for(i in values.size-period until values.size){ val d=values[i]-values[i-1]; if(d>=0) gains+=d else losses-=d }
    if(losses==0.0) return 100.0
    val rs=(gains/period)/(losses/period)
    return 100.0-100.0/(1.0+rs)
}

@Composable fun MarketChartCard(symbol:String, intervalLabel:String, candles:List<Candle>, modifier:Modifier=Modifier){
    val visible=if(candles.size>60)candles.takeLast(60) else candles
    val closes=visible.map{it.close}; val e20=emaSeries(closes,20); val e50=emaSeries(closes,50); val rsi=rsiValue(closes)
    Card(modifier.fillMaxWidth(),shape=RoundedCornerShape(18.dp)){
        Column(Modifier.padding(14.dp),verticalArrangement=Arrangement.spacedBy(8.dp)){
            Text("$symbol · $intervalLabel · BINANCE",fontWeight=FontWeight.Bold,fontSize=18.sp)
            if(visible.size<2) Text("차트 데이터를 불러오는 중입니다.",color=Color.Gray) else {
                Row(Modifier.fillMaxWidth(),horizontalArrangement=Arrangement.SpaceBetween){
                    Text("EMA20 ${fmtChart(e20.lastOrNull())}",color=Color(0xFF35A7FF),fontSize=13.sp)
                    Text("EMA50 ${fmtChart(e50.lastOrNull())}",color=Color(0xFFFFA000),fontSize=13.sp)
                    Text("RSI ${String.format(Locale.KOREA,"%.1f",rsi)}",color=Color(0xFFA875FF),fontSize=13.sp)
                }
                CandlestickCanvas(visible,e20,e50)
                Text("RSI 14  ${String.format(Locale.KOREA,"%.2f",rsi)}",color=Color(0xFFA875FF),fontSize=13.sp)
                RsiCanvas(closes)
                Row(Modifier.fillMaxWidth(),horizontalArrangement=Arrangement.SpaceBetween){
                    Text("▲ LONG 후보",color=Color(0xFF21D58B),fontWeight=FontWeight.Bold,fontSize=12.sp)
                    Text("▼ SHORT 후보",color=Color(0xFFFF4058),fontWeight=FontWeight.Bold,fontSize=12.sp)
                }
            }
        }
    }
}

@Composable private fun CandlestickCanvas(candles:List<Candle>,e20:List<Double>,e50:List<Double>){
    val up=Color(0xFF18C98B); val down=Color(0xFFFF4058); val blue=Color(0xFF2196F3); val orange=Color(0xFFFFA000); val grid=Color(0xFF29313D)
    Canvas(Modifier.fillMaxWidth().height(330.dp).background(Color(0xFF090E16),RoundedCornerShape(12.dp))){
        val maxP=candles.maxOf{it.high}; val minP=candles.minOf{it.low}; val raw=maxP-minP; val range=if(raw<=0)1.0 else raw; val pad=range*.12; val top=maxP+pad; val bottom=minP-pad; val full=top-bottom
        fun y(v:Double)=((top-v)/full*size.height).toFloat()
        for(g in 1..5){val gy=size.height*g/6f;drawLine(grid,Offset(0f,gy),Offset(size.width,gy),1f)}
        val step=size.width/candles.size; val bw=max(2f,step*.58f)
        candles.forEachIndexed{i,c-> val x=step*i+step/2; val col=if(c.close>=c.open)up else down; val yo=y(c.open);val yc=y(c.close);drawLine(col,Offset(x,y(c.high)),Offset(x,y(c.low)),1.4f);drawRect(col,Offset(x-bw/2,min(yo,yc)),Size(bw,max(2f,abs(yc-yo))))}
        fun line(series:List<Double>,col:Color){if(series.size<2)return;val p=Path();series.forEachIndexed{i,v->val q=Offset(step*i+step/2,y(v));if(i==0)p.moveTo(q.x,q.y) else p.lineTo(q.x,q.y)};drawPath(p,col,style=Stroke(2.5f))}
        line(e20,blue);line(e50,orange)
        // Signal candidates: EMA20/EMA50 crossovers. Mark only meaningful crossover points.
        for(i in 1 until candles.size){
            val prev=e20[i-1]-e50[i-1]; val now=e20[i]-e50[i]; val x=step*i+step/2
            if(prev<=0 && now>0){ val yy=y(candles[i].low)+18f; drawCircle(up,8f,Offset(x,yy)); drawLine(up,Offset(x,yy-18f),Offset(x,yy-4f),5f) }
            if(prev>=0 && now<0){ val yy=y(candles[i].high)-18f; drawCircle(down,8f,Offset(x,yy)); drawLine(down,Offset(x,yy+4f),Offset(x,yy+18f),5f) }
        }
        val ly=y(candles.last().close);drawLine(up.copy(alpha=.7f),Offset(0f,ly),Offset(size.width,ly),1.4f)
    }
}

@Composable private fun RsiCanvas(closes:List<Double>){
    val purple=Color(0xFF8E6CFF);val guide=Color(0xFF565B66);val series=mutableListOf<Double>();for(i in closes.indices)series+=if(i<14)50.0 else rsiValue(closes.take(i+1),14)
    Canvas(Modifier.fillMaxWidth().height(100.dp).background(Color(0xFF090E16),RoundedCornerShape(10.dp))){fun y(v:Double)=((100-v)/100*size.height).toFloat();drawLine(guide,Offset(0f,y(70.0)),Offset(size.width,y(70.0)),1f);drawLine(guide,Offset(0f,y(30.0)),Offset(size.width,y(30.0)),1f);if(series.size>1){val step=size.width/series.size;val p=Path();series.forEachIndexed{i,v->val q=Offset(step*i+step/2,y(v));if(i==0)p.moveTo(q.x,q.y)else p.lineTo(q.x,q.y)};drawPath(p,purple,style=Stroke(2.4f))}}
}
private fun fmtChart(v:Double?)=if(v==null)"-" else String.format(Locale.KOREA,"%,.2f",v)
