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
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import androidx.work.*
import java.util.Locale
import java.util.concurrent.TimeUnit

class MainActivity : ComponentActivity() {
    private val notifPermission = registerForActivityResult(ActivityResultContracts.RequestPermission()) {}
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        if (android.os.Build.VERSION.SDK_INT >= 33 && checkSelfPermission(Manifest.permission.POST_NOTIFICATIONS) != PackageManager.PERMISSION_GRANTED) notifPermission.launch(Manifest.permission.POST_NOTIFICATIONS)
        (getSystemService(NOTIFICATION_SERVICE) as NotificationManager).createNotificationChannel(NotificationChannel("signals", "캐치월드 기회 알림", NotificationManager.IMPORTANCE_HIGH))
        val req = PeriodicWorkRequestBuilder<SignalWorker>(15, TimeUnit.MINUTES).setConstraints(Constraints.Builder().setRequiredNetworkType(NetworkType.CONNECTED).build()).build()
        WorkManager.getInstance(this).enqueueUniquePeriodicWork("catchworld-signal", ExistingPeriodicWorkPolicy.UPDATE, req)
        setContent { CatchWorldApp() }
    }
}

private val Bg=Color(0xFF070B12); private val Surface=Color(0xFF111722); private val Surface2=Color(0xFF171F2C); private val Accent=Color(0xFF7A6CFF); private val Green=Color(0xFF19D38A); private val Red=Color(0xFFFF5B6E); private val Amber=Color(0xFFFFB74D); private val Muted=Color(0xFF9BA6B5)
private data class LiveSignal(val market:String,val state:String,val score:Int,val price:Double,val vr:Double,val rsi:Double,val ret1h:Double,val reason:String)

@Composable private fun liveSignal(): LiveSignal {
    val ctx=LocalContext.current
    val p=remember(ctx){AppStore.prefs(ctx)}
    var tick by remember { mutableLongStateOf(System.currentTimeMillis()) }
    LaunchedEffect(Unit){ while(true){ kotlinx.coroutines.delay(5000); tick=System.currentTimeMillis() } }
    return remember(tick){ LiveSignal(
        p.getString("catchworld_market","KRW-BTC")?:"KRW-BTC",
        p.getString("catchworld_state","WATCH")?:"WATCH",
        p.getInt("catchworld_score",0),
        p.getString("catchworld_price","0")?.toDoubleOrNull()?:0.0,
        p.getString("catchworld_vr1h","0")?.toDoubleOrNull()?:0.0,
        p.getString("catchworld_rsi","0")?.toDoubleOrNull()?:0.0,
        p.getString("catchworld_ret1h","0")?.toDoubleOrNull()?:0.0,
        p.getString("catchworld_reason","신호 수집 대기")?:"신호 수집 대기") }
}

@Composable fun CatchWorldApp(){ var tab by remember{mutableIntStateOf(0)}; val tabs=listOf("홈","레이더","차트","자산","알림"); MaterialTheme(colorScheme=darkColorScheme(primary=Accent,background=Bg,surface=Surface,surfaceVariant=Surface2)){ Scaffold(containerColor=Bg,bottomBar={NavigationBar(containerColor=Color(0xFF0C111A)){tabs.forEachIndexed{i,t->NavigationBarItem(selected=tab==i,onClick={tab=i},icon={Text(listOf("⌂","◎","⌁","◆","◉")[i],fontSize=18.sp)},label={Text(t)})}}}){pad->Box(Modifier.fillMaxSize().padding(pad).background(Bg)){when(tab){0->HomeScreen();1->RadarScreen();2->ChartScreen();3->AssetScreen();else->AlertScreen()}}}}}
@Composable private fun Header(t:String,s:String){Column{Row(verticalAlignment=Alignment.Bottom){Text(t,fontSize=28.sp,fontWeight=FontWeight.ExtraBold);Spacer(Modifier.width(8.dp));Text("v2.7",color=Accent,fontWeight=FontWeight.Bold)};Text(s,color=Muted,fontSize=13.sp)}}
private fun fmt(v:Double)=if(v==0.0)"-" else String.format(Locale.KOREA,"%,.2f",v)
@Composable private fun HomeScreen(){val x=liveSignal();LazyColumn(Modifier.fillMaxSize().statusBarsPadding().padding(horizontal=14.dp),contentPadding=PaddingValues(top=14.dp,bottom=24.dp),verticalArrangement=Arrangement.spacedBy(12.dp)){item{Header("캐치월드","실시간 자금 흐름 금융 레이더")};item{Row(horizontalArrangement=Arrangement.spacedBy(8.dp)){MarketChip(x.market.removePrefix("KRW-"),fmt(x.price),Modifier.weight(1f));MarketChip("상태",x.state,Modifier.weight(1f));MarketChip("점수",x.score.toString(),Modifier.weight(1f));MarketChip("VR",String.format(Locale.US,"%.1fx",x.vr),Modifier.weight(1f))}};item{SectionTitle("실시간 신호")};item{OpportunityCard("${x.market} · ${x.state}","가격 ${fmt(x.price)} · VR ${String.format(Locale.US,"%.2fx",x.vr)} · RSI ${String.format(Locale.US,"%.1f",x.rsi)} · 1h ${String.format(Locale.US,"%+.2f%%",x.ret1h*100)}",x.score.toString(),stateColor(x.state))};item{OpportunityCard("판정 이유",x.reason,x.state,stateColor(x.state))};item{OpportunityCard("금 · ETF · 예금","통합 기회점수 엔진 준비 완료 · 실데이터 연결 예정","준비",Accent)}}}
@Composable private fun RadarScreen(){val x=liveSignal();LazyColumn(Modifier.fillMaxSize().statusBarsPadding().padding(horizontal=14.dp),contentPadding=PaddingValues(top=14.dp,bottom=24.dp),verticalArrangement=Arrangement.spacedBy(10.dp)){item{Header("레이더","현재 감시 코인의 자금 상태")};item{OpportunityCard("🐋 ${x.market}","거래대금 ${String.format(Locale.US,"%.2fx",x.vr)} · RSI ${String.format(Locale.US,"%.1f",x.rsi)}",x.state,stateColor(x.state))};item{OpportunityCard("자금 흐름","${String.format(Locale.US,"%+.2f%%",x.ret1h*100)} / 1시간 · ${x.reason}","${x.score}점",stateColor(x.state))};item{OpportunityCard("상태 흐름","WATCH → WHALE → HOLDING → PRE-BLUE → BLUE → EXIT_RISK","실시간",Accent)}}}
@Composable private fun ChartScreen(){val x=liveSignal();LazyColumn(Modifier.fillMaxSize().statusBarsPadding().padding(horizontal=14.dp),contentPadding=PaddingValues(top=14.dp,bottom=24.dp),verticalArrangement=Arrangement.spacedBy(12.dp)){item{Header("차트","가격과 자금흐름 마커")};item{OpportunityCard(x.market,"현재 ${fmt(x.price)} · ${x.state} · VR ${String.format(Locale.US,"%.2fx",x.vr)}","차트연결 전",Accent)};item{Card(colors=CardDefaults.cardColors(containerColor=Surface),shape=RoundedCornerShape(20.dp)){Box(Modifier.fillMaxWidth().height(220.dp).padding(18.dp).background(Surface2,RoundedCornerShape(14.dp)),contentAlignment=Alignment.Center){Text("캔들 차트 렌더러 연결 예정",color=Muted)}}}}}
@Composable private fun AssetScreen(){LazyColumn(Modifier.fillMaxSize().statusBarsPadding().padding(horizontal=14.dp),contentPadding=PaddingValues(top=14.dp,bottom=24.dp),verticalArrangement=Arrangement.spacedBy(10.dp)){item{Header("자산","코인·금·ETF·예금 통합")};item{AssetCard("금","기회점수 엔진 연결됨 · 실데이터 공급자 연결 전")};item{AssetCard("ETF","기회점수 엔진 연결됨 · 실데이터 공급자 연결 전")};item{AssetCard("예금·적금","금리 점수 엔진 연결됨 · 실데이터 공급자 연결 전")};item{AssetCard("자산금고","보유자산 관리 영역")}}}
@Composable private fun AlertScreen(){val x=liveSignal();LazyColumn(Modifier.fillMaxSize().statusBarsPadding().padding(horizontal=14.dp),contentPadding=PaddingValues(top=14.dp,bottom=24.dp),verticalArrangement=Arrangement.spacedBy(10.dp)){item{Header("알림","실시간 판정 결과")};item{AlertCard(x.state,"${x.market} · ${x.score}점",x.reason)};item{Text("PRE-BLUE · BLUE · EXIT_RISK는 백그라운드 알림과 연결됨",color=Muted,fontSize=12.sp)}}}
@Composable private fun MarketChip(t:String,v:String,m:Modifier=Modifier){Card(modifier=m,colors=CardDefaults.cardColors(containerColor=Surface),shape=RoundedCornerShape(14.dp)){Column(Modifier.padding(10.dp)){Text(t,fontWeight=FontWeight.Bold);Text(v,color=Muted,fontSize=10.sp,maxLines=1)}}}
@Composable private fun OpportunityCard(t:String,b:String,s:String,a:Color){Card(colors=CardDefaults.cardColors(containerColor=Surface),shape=RoundedCornerShape(18.dp)){Row(Modifier.fillMaxWidth().padding(16.dp),horizontalArrangement=Arrangement.SpaceBetween){Column(Modifier.weight(1f)){Text(t,fontWeight=FontWeight.Bold,fontSize=18.sp);Text(b,color=Muted,fontSize=13.sp)};Spacer(Modifier.width(10.dp));Surface(color=a.copy(alpha=.15f),shape=RoundedCornerShape(50)){Text(s,color=a,fontWeight=FontWeight.Bold,fontSize=11.sp,modifier=Modifier.padding(horizontal=10.dp,vertical=6.dp))}}}}
@Composable private fun AssetCard(t:String,b:String){Card(colors=CardDefaults.cardColors(containerColor=Surface),shape=RoundedCornerShape(18.dp)){Column(Modifier.padding(16.dp)){Text(t,fontWeight=FontWeight.ExtraBold,fontSize=20.sp);Text(b,color=Muted,fontSize=13.sp)}}}
@Composable private fun AlertCard(s:String,t:String,d:String){val c=stateColor(s);Card(colors=CardDefaults.cardColors(containerColor=Surface),shape=RoundedCornerShape(18.dp)){Row(Modifier.fillMaxWidth().padding(16.dp),horizontalArrangement=Arrangement.spacedBy(12.dp)){Surface(color=c.copy(alpha=.15f),shape=RoundedCornerShape(12.dp)){Text(s,color=c,fontWeight=FontWeight.ExtraBold,modifier=Modifier.padding(10.dp))};Column{Text(t,fontWeight=FontWeight.Bold);Text(d,color=Muted,fontSize=12.sp)}}}}
@Composable private fun SectionTitle(t:String){Text(t,fontSize=20.sp,fontWeight=FontWeight.ExtraBold)}
private fun stateColor(s:String)=when(s){"BLUE"->Color(0xFF55C2FF);"PRE_BLUE","PRE-BLUE"->Accent;"WHALE","HOLDING"->Amber;"EXIT_RISK"->Red;else->Muted}
