package com.daon.futures

import androidx.compose.foundation.Canvas
import androidx.compose.foundation.background
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.Card
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

fun emaSeries(values:List<Double>,period:Int):List<Double>{if(values.isEmpty())return emptyList();val k=2.0/(period+1.0);val out=MutableList(values.size){0.0};var ema=values.first();out[0]=ema;for(i in 1 until values.size){ema=values[i]*k+ema*(1.0-k);out[i]=ema};return out}
fun rsiValue(values:List<Double>,period:Int=14):Double{if(values.size<=period)return 50.0;var gains=0.0;var losses=0.0;for(i in values.size-period until values.size){val d=values[i]-values[i-1];if(d>=0)gains+=d else losses-=d};if(losses==0.0)return 100.0;val rs=(gains/period)/(losses/period);return 100.0-100.0/(1.0+rs)}

private data class OneCandleZone(val index:Int,val low:Double,val high:Double,val side:String,val retested:Boolean,val confirmed:Boolean,val entry:Double?,val stop:Double?,val target2R:Double?)
private fun oneCandleZone(candles:List<Candle>,e20:List<Double>,e50:List<Double>):OneCandleZone?{
    if(candles.size<22||e20.isEmpty()||e50.isEmpty())return null
    val bullish=e20.last()>e50.last(); val start=maxOf(0,candles.size-21); val end=candles.size-1; val indexed=(start until end).map{it to candles[it]}
    val key=if(bullish) indexed.filter{(_,c)->c.close<c.open}.maxByOrNull{(_,c)->c.high} else indexed.filter{(_,c)->c.close>c.open}.minByOrNull{(_,c)->c.low} ?: return null
    val(idx,c)=key; val low=minOf(c.open,c.close); val high=maxOf(c.open,c.close); val after=candles.drop(idx+1); val retested=after.any{it.low<=high&&it.high>=low}; val last=candles.last()
    val confirmed=retested && if(bullish) last.close>high else last.close<low
    if(!confirmed)return OneCandleZone(idx,low,high,if(bullish)"LONG" else "SHORT",retested,false,null,null,null)
    val entry=last.close; val stop=if(bullish)low else high; val risk=if(bullish)entry-stop else stop-entry
    if(risk<=0.0)return OneCandleZone(idx,low,high,if(bullish)"LONG" else "SHORT",retested,false,null,null,null)
    val target=if(bullish)entry+risk*2 else entry-risk*2
    return OneCandleZone(idx,low,high,if(bullish)"LONG" else "SHORT",true,true,entry,stop,target)
}

@Composable fun MarketChartCard(symbol:String,intervalLabel:String,candles:List<Candle>,modifier:Modifier=Modifier){
    val visible=if(candles.size>60)candles.takeLast(60) else candles; val closes=visible.map{it.close}; val e20=emaSeries(closes,20); val e50=emaSeries(closes,50); val rsi=rsiValue(closes); val zone=oneCandleZone(visible,e20,e50)
    Card(modifier=modifier.fillMaxWidth(),shape=RoundedCornerShape(18.dp)){Column(Modifier.padding(14.dp),verticalArrangement=Arrangement.spacedBy(8.dp)){
        Text("$symbol · $intervalLabel · BINANCE",fontWeight=FontWeight.Bold,fontSize=18.sp)
        if(visible.size<2)Text("차트 데이터를 불러오는 중입니다.",color=Color.Gray) else {
            Row(Modifier.fillMaxWidth(),horizontalArrangement=Arrangement.SpaceBetween){Text("EMA20 ${fmtChart(e20.lastOrNull())}",color=Color(0xFF35A7FF),fontSize=13.sp);Text("EMA50 ${fmtChart(e50.lastOrNull())}",color=Color(0xFFFFA000),fontSize=13.sp);Text("RSI ${String.format(Locale.KOREA,"%.1f",rsi)}",color=Color(0xFFA875FF),fontSize=13.sp)}
            zone?.let{val col=if(it.side=="LONG")Color(0xFF21D58B) else Color(0xFFFF4058);val state=when{it.confirmed->"진입 확정";it.retested->"리테스트 확인 · 방향 확인 대기";else->"리테스트 대기"};Text("One Candle ${it.side} · 기준 ${fmtChart(it.low)} ~ ${fmtChart(it.high)} · $state",color=col,fontWeight=FontWeight.Bold,fontSize=12.sp)}?:Text("One Candle · 기준 캔들 탐색 중",color=Color.Gray,fontSize=12.sp)
            CandlestickCanvas(visible,e20,e50,zone)
            zone?.takeIf{it.confirmed}?.let{Text("진입 ${fmtChart(it.entry)} · SL ${fmtChart(it.stop)} · 2R ${fmtChart(it.target2R)}",color=if(it.side=="LONG")Color(0xFF21D58B) else Color(0xFFFF4058),fontWeight=FontWeight.Bold,fontSize=12.sp)}
            Text("RSI 14  ${String.format(Locale.KOREA,"%.2f",rsi)}",color=Color(0xFFA875FF),fontSize=13.sp);RsiCanvas(closes)
        }
    }}
}

@Composable private fun CandlestickCanvas(candles:List<Candle>,e20:List<Double>,e50:List<Double>,zone:OneCandleZone?){
    val up=Color(0xFF18C98B);val down=Color(0xFFFF4058);val blue=Color(0xFF2196F3);val orange=Color(0xFFFFA000);val grid=Color(0xFF29313D)
    Canvas(Modifier.fillMaxWidth().height(360.dp).background(Color(0xFF090E16),RoundedCornerShape(12.dp))){
        val extras=buildList{zone?.let{add(it.low);add(it.high);it.stop?.let(::add);it.target2R?.let(::add)}};val maxP=max(candles.maxOf{it.high},extras.maxOrNull()?:candles.maxOf{it.high});val minP=min(candles.minOf{it.low},extras.minOrNull()?:candles.minOf{it.low});val range=(maxP-minP).let{if(it<=0)1.0 else it};val pad=range*.12;val top=maxP+pad;val bottom=minP-pad;val full=top-bottom;fun y(v:Double)=((top-v)/full*size.height).toFloat()
        val plotWidth=size.width*.88f
        for(g in 1..5){val gy=size.height*g/6f;drawLine(grid,Offset(0f,gy),Offset(plotWidth,gy),1f)}
        val step=plotWidth/candles.size;val body=max(2f,step*.58f)
        zone?.let{val c=if(it.side=="LONG")up else down;val left=(step*it.index).coerceAtLeast(0f);val ty=min(y(it.high),y(it.low));val by=max(y(it.high),y(it.low));drawRect(c.copy(alpha=.20f),Offset(left,ty),Size(plotWidth-left,max(3f,by-ty)));drawLine(c,Offset(left,ty),Offset(plotWidth,ty),2f);drawLine(c,Offset(left,by),Offset(plotWidth,by),2f)}
        candles.forEachIndexed{i,c->val x=step*i+step/2;val cc=if(c.close>=c.open)up else down;val oy=y(c.open);val cy=y(c.close);drawLine(cc,Offset(x,y(c.high)),Offset(x,y(c.low)),1.4f);drawRect(cc,Offset(x-body/2,min(oy,cy)),Size(body,max(2f,abs(cy-oy))))}
        fun drawEma(s:List<Double>,c:Color){if(s.size>=2){val p=Path();s.forEachIndexed{i,v->val pt=Offset(step*i+step/2,y(v));if(i==0)p.moveTo(pt.x,pt.y) else p.lineTo(pt.x,pt.y)};drawPath(p,c,style=Stroke(2.5f))}};drawEma(e20,blue);drawEma(e50,orange)
        zone?.takeIf{it.confirmed}?.let{val entry=it.entry?:return@let;val stop=it.stop?:return@let;val target=it.target2R?:return@let;val c=if(it.side=="LONG")up else down;drawLine(c,Offset(0f,y(entry)),Offset(plotWidth,y(entry)),1.8f);drawLine(down,Offset(0f,y(stop)),Offset(plotWidth,y(stop)),2.2f);drawLine(up,Offset(0f,y(target)),Offset(plotWidth,y(target)),2.2f);drawCircle(c,8f,Offset(plotWidth-8f,y(entry)))}
        drawLine(Color.White.copy(alpha=.35f),Offset(0f,y(candles.last().close)),Offset(plotWidth,y(candles.last().close)),1.2f)
    }
}
@Composable private fun RsiCanvas(closes:List<Double>){val purple=Color(0xFF8E6CFF);val guide=Color(0xFF565B66);val series=mutableListOf<Double>();for(i in closes.indices)series+=if(i<14)50.0 else rsiValue(closes.take(i+1),14);Canvas(Modifier.fillMaxWidth().height(100.dp).background(Color(0xFF090E16),RoundedCornerShape(10.dp))){fun y(v:Double)=((100-v)/100*size.height).toFloat();drawLine(guide,Offset(0f,y(70.0)),Offset(size.width,y(70.0)),1f);drawLine(guide,Offset(0f,y(30.0)),Offset(size.width,y(30.0)),1f);if(series.size>1){val step=size.width/series.size;val p=Path();series.forEachIndexed{i,v->val pt=Offset(step*i+step/2,y(v));if(i==0)p.moveTo(pt.x,pt.y)else p.lineTo(pt.x,pt.y)};drawPath(p,purple,style=Stroke(2.4f))}}}
private fun fmtChart(v:Double?):String=if(v==null)"-" else String.format(Locale.KOREA,"%,.2f",v)