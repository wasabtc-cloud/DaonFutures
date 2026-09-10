package com.daon.futures

import android.Manifest
import android.app.NotificationChannel
import android.app.NotificationManager
import android.content.Context
import android.content.pm.PackageManager
import android.os.Bundle
import androidx.activity.ComponentActivity
import androidx.activity.compose.setContent
import androidx.activity.result.contract.ActivityResultContracts
import androidx.compose.foundation.background
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import androidx.glance.appwidget.updateAll
import androidx.work.*
import com.daon.futures.widget.DaonWidget
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext
import java.text.SimpleDateFormat
import java.util.*
import java.util.concurrent.TimeUnit

class MainActivity:ComponentActivity(){
 private val notifPermission=registerForActivityResult(ActivityResultContracts.RequestPermission()){}
 override fun onCreate(savedInstanceState:Bundle?){super.onCreate(savedInstanceState);if(android.os.Build.VERSION.SDK_INT>=33&&checkSelfPermission(Manifest.permission.POST_NOTIFICATIONS)!=PackageManager.PERMISSION_GRANTED)notifPermission.launch(Manifest.permission.POST_NOTIFICATIONS);(getSystemService(NOTIFICATION_SERVICE)as NotificationManager).createNotificationChannel(NotificationChannel("signals","매매 신호",NotificationManager.IMPORTANCE_HIGH));val req=PeriodicWorkRequestBuilder<SignalWorker>(15,TimeUnit.MINUTES).setConstraints(Constraints.Builder().setRequiredNetworkType(NetworkType.CONNECTED).build()).build();WorkManager.getInstance(this).enqueueUniquePeriodicWork("daon-signal",ExistingPeriodicWorkPolicy.UPDATE,req);setContent{DaonApp()}}
}
@Composable fun DaonApp(){
 val context=LocalContext.current;val prefs=remember{AppStore.prefs(context)};val scope=rememberCoroutineScope();var symbol by remember{mutableStateOf(prefs.getString("symbol","BTCUSDT")!!)};var sl by remember{mutableFloatStateOf(prefs.getFloat("sl",1f))};var tp by remember{mutableFloatStateOf(prefs.getFloat("tp",1.5f))};var lev by remember{mutableIntStateOf(prefs.getInt("lev",3))};var notifications by remember{mutableStateOf(prefs.getBoolean("notifications",true))};var signal by remember{mutableStateOf<Signal?>(null)};var price by remember{mutableDoubleStateOf(0.0)};var loading by remember{mutableStateOf(false)};var refreshToken by remember{mutableIntStateOf(0)};val history=remember(refreshToken){AppStore.history(context)}
 MaterialTheme(colorScheme=darkColorScheme(primary=Color(0xFF7C9CFF),background=Color(0xFF0D0F14),surface=Color(0xFF171A21))){LazyColumn(Modifier.fillMaxSize().background(MaterialTheme.colorScheme.background).padding(16.dp),verticalArrangement=Arrangement.spacedBy(12.dp)){
 item{Text("다온이 선물매매",fontSize=28.sp,fontWeight=FontWeight.Bold);Text("v2.0 · 4H/1H 추세 + 15M 진입",color=Color.LightGray)}
 item{Card(shape=RoundedCornerShape(18.dp)){Column(Modifier.padding(16.dp),verticalArrangement=Arrangement.spacedBy(10.dp)){Text("종목",fontWeight=FontWeight.Bold);Row(horizontalArrangement=Arrangement.spacedBy(8.dp)){listOf("BTCUSDT","ETHUSDT").forEach{s->FilterChip(selected=symbol==s,onClick={symbol=s;save(context,symbol,sl,tp,lev,notifications);refreshToken++},label={Text(s)})}}}}}
 item{Card(shape=RoundedCornerShape(18.dp)){Column(Modifier.padding(16.dp),verticalArrangement=Arrangement.spacedBy(10.dp)){Text("매매 설정",fontWeight=FontWeight.Bold);Text("손절 ${String.format(Locale.KOREA,"%.1f",sl)}% · 익절 ${String.format(Locale.KOREA,"%.1f",tp)}% · 레버리지 ${lev}배",fontSize=18.sp);Text("손절");Slider(value=sl,onValueChange={sl=it},valueRange=0.5f..3f,steps=5,onValueChangeFinished={save(context,symbol,sl,tp,lev,notifications)});Text("익절");Slider(value=tp,onValueChange={tp=it},valueRange=0.5f..5f,steps=9,onValueChangeFinished={save(context,symbol,sl,tp,lev,notifications)});Text("레버리지");Row(horizontalArrangement=Arrangement.spacedBy(8.dp)){listOf(1,2,3).forEach{i->FilterChip(selected=lev==i,onClick={lev=i;save(context,symbol,sl,tp,lev,notifications)},label={Text("${i}배")})}};Row(Modifier.fillMaxWidth(),horizontalArrangement=Arrangement.SpaceBetween){Column{Text("푸시 알림",fontWeight=FontWeight.Bold);Text("신호 발생 시 알림",fontSize=12.sp,color=Color.Gray)};Switch(checked=notifications,onCheckedChange={notifications=it;save(context,symbol,sl,tp,lev,notifications)})}}}}
 item{Card(shape=RoundedCornerShape(18.dp)){Column(Modifier.padding(18.dp),verticalArrangement=Arrangement.spacedBy(9.dp)){Text("현재가",fontWeight=FontWeight.Bold);Text(if(price>0)String.format(Locale.KOREA,"%,.2f",price)else "-");Text("최근 신호",fontWeight=FontWeight.Bold);Text(when(signal?.side){"LONG"->"🟢 LONG";"SHORT"->"🔴 SHORT";else->"⚪ 대기"},fontSize=30.sp,fontWeight=FontWeight.Bold);signal?.let{s->Text("진입  ${fmt(s.price)}");Text("SL     ${fmt(s.sl)}");Text("TP     ${fmt(s.tp)}");Text("RSI    ${String.format(Locale.KOREA,"%.1f",s.rsi)}");Text(s.reason,color=Color.LightGray,fontSize=12.sp)};Button(enabled=!loading,onClick={scope.launch{loading=true;save(context,symbol,sl,tp,lev,notifications);try{price=withContext(Dispatchers.IO){BinanceApi.price(symbol)};signal=withContext(Dispatchers.IO){BinanceApi.analyze(symbol,sl.toDouble(),tp.toDouble())};val e=prefs.edit().putString("last_symbol",symbol).putString("last_price",fmt(price)).putString("last_updated",fmtDate(System.currentTimeMillis()));signal?.let{e.putString("last_side",it.side).putString("last_sl",fmt(it.sl)).putString("last_tp",fmt(it.tp)).putString("last_rsi",String.format(Locale.US,"%.1f",it.rsi)).putString("last_reason",it.reason).putLong("last_candle",it.candleTime);AppStore.addHistory(context,it,symbol)}?:run{e.putString("last_side","WAIT").putString("last_sl","-").putString("last_tp","-").putString("last_rsi","-")};e.apply();DaonWidget().updateAll(context);refreshToken++}finally{loading=false}}}){Text(if(loading)"분석 중…"else "지금 분석")}}}}
 item{Text("📊 최근 신호 기록",fontSize=20.sp,fontWeight=FontWeight.Bold)};if(history.isEmpty())item{Text("아직 신호 기록이 없습니다.",color=Color.Gray)}else items(history){r->Card(shape=RoundedCornerShape(14.dp),modifier=Modifier.fillMaxWidth()){Column(Modifier.padding(14.dp)){Text("${r.symbol}  ${if(r.side=="LONG")"🟢 LONG"else"🔴 SHORT"}",fontWeight=FontWeight.Bold);Text("진입 ${fmt(r.price)}  ·  SL ${fmt(r.sl)}  ·  TP ${fmt(r.tp)}");Text("RSI ${String.format(Locale.KOREA,"%.1f",r.rsi)}  ·  ${fmtDate(r.timestamp)}",fontSize=12.sp,color=Color.Gray)}}}
 item{val risk=AppStore.riskStatus(context);Card(shape=RoundedCornerShape(18.dp)){Column(Modifier.padding(16.dp),verticalArrangement=Arrangement.spacedBy(9.dp)){Text("🛡 매매 안전장치",fontWeight=FontWeight.Bold,fontSize=19.sp);Text("오늘 순손익  ${risk.pnl.toLocaleWon()}  ·  연속손실 ${risk.consecutiveLosses}/2",fontSize=18.sp);Text(if(risk.locked)"🔴 오늘 매매 종료 — 안전장치가 작동했습니다."else"🟢 거래 가능 — 1회 -5,000원 권장 / 하루 -20,000원 제한",color=if(risk.locked)Color(0xFFFF6B6B)else Color(0xFF8EE0A8),fontWeight=FontWeight.Bold);Row(horizontalArrangement=Arrangement.spacedBy(8.dp)){OutlinedButton(onClick={AppStore.recordResult(context,false,5000);refreshToken++}){Text("손실 -5천")};OutlinedButton(onClick={AppStore.recordResult(context,true,5000);refreshToken++}){Text("수익 +5천")};OutlinedButton(onClick={AppStore.resetRisk(context);refreshToken++}){Text("초기화")}};Text("※ 실제 손익을 수동으로 기록하는 기능입니다. 거래소의 실현손익과 자동 연동되지는 않습니다.",fontSize=12.sp,color=Color.Gray)}}}
 item{Card(shape=RoundedCornerShape(18.dp)){Column(Modifier.padding(16.dp),verticalArrangement=Arrangement.spacedBy(7.dp)){Text("⚠️ 사용 전 확인",fontWeight=FontWeight.Bold);Text("이 앱은 신호 보조용입니다. 실제 주문·청산은 반드시 거래소에서 직접 확인하세요.",fontSize=13.sp,color=Color.LightGray);Text("위젯과 백그라운드 확인은 Android 전원관리로 지연될 수 있습니다.",fontSize=13.sp,color=Color.Gray)}}}
 }}}
fun save(c:Context,symbol:String,sl:Float,tp:Float,lev:Int,notifications:Boolean)=AppStore.saveSettings(c,symbol,sl,tp,lev,notifications)
fun fmt(v:Double)=String.format(Locale.KOREA,"%,.2f",v)
fun fmtDate(v:Long)=SimpleDateFormat("MM/dd HH:mm",Locale.KOREA).format(Date(v))
private fun Int.toLocaleWon():String=String.format(Locale.KOREA,"%+,d원",this)
