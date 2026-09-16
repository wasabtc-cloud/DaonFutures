package com.daon.futures

import android.Manifest
import android.app.NotificationChannel
import android.app.NotificationManager
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
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import androidx.work.*
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
private data class RadarModule(val name:String,val subtitle:String,val state:String,val detail:String)

@Composable fun CatchWorldApp(){var tab by remember{mutableIntStateOf(0)};val tabs=listOf("홈","레이더","차트","자산","알림");MaterialTheme(colorScheme=darkColorScheme(primary=Accent,background=Bg,surface=Surface,surfaceVariant=Surface2)){Scaffold(containerColor=Bg,bottomBar={NavigationBar(containerColor=Color(0xFF0C111A)){tabs.forEachIndexed{i,t->NavigationBarItem(selected=tab==i,onClick={tab=i},icon={Text(listOf("⌂","◎","⌁","◆","◉")[i],fontSize=18.sp)},label={Text(t)})}}}){pad->Box(Modifier.fillMaxSize().padding(pad).background(Bg)){when(tab){0->HomeScreen();1->RadarScreen();2->ChartScreen();3->AssetScreen();else->AlertScreen()}}}}}
@Composable private fun Header(title:String,subtitle:String){Column(verticalArrangement=Arrangement.spacedBy(4.dp)){Row(verticalAlignment=Alignment.Bottom){Text(title,fontSize=28.sp,fontWeight=FontWeight.ExtraBold);Spacer(Modifier.width(8.dp));Text("v2.6",color=Accent,fontWeight=FontWeight.Bold)};Text(subtitle,color=Muted,fontSize=13.sp)}}
@Composable private fun HomeScreen(){LazyColumn(Modifier.fillMaxSize().statusBarsPadding().padding(horizontal=14.dp),contentPadding=PaddingValues(top=14.dp,bottom=24.dp),verticalArrangement=Arrangement.spacedBy(12.dp)){item{Header("캐치월드","지금 돈이 어디로 들어가고 있는지 찾는 금융 레이더")};item{Row(horizontalArrangement=Arrangement.spacedBy(8.dp)){MarketChip("BTC","연결 대기",Modifier.weight(1f));MarketChip("금","자산탭",Modifier.weight(1f));MarketChip("ETF","자산탭",Modifier.weight(1f));MarketChip("예금","비교 예정",Modifier.weight(1f))}};item{SectionTitle("오늘의 기회")};item{OpportunityCard("🔥 급등 가능성 TOP 3","9AM · Daily Surge 결과 연결 대기","연구중",Amber)};item{OpportunityCard("💰 자금유입 감지","Accumulation 결과를 이 카드에 연결","연구중",Green)};item{OpportunityCard("⏰ 09:00 후보","08:55 예측 → 09:00 확인 구조","분석중",Accent)};item{OpportunityCard("🧠 패턴 레이더","Wonyotti-inspired 패턴 유사도 기반","백테스트중",Color(0xFF55C2FF))};item{Card(colors=CardDefaults.cardColors(containerColor=Surface),shape=RoundedCornerShape(20.dp)){Column(Modifier.padding(16.dp),verticalArrangement=Arrangement.spacedBy(8.dp)){Text("신호 상태 흐름",fontWeight=FontWeight.Bold,fontSize=18.sp);Text("관심 → 자금유입 → PRE-BLUE → BLUE → GREEN",color=Muted);Text("검증 완료 전략만 실제 알림 대상으로 승격",color=Green,fontWeight=FontWeight.Bold,fontSize=13.sp)}}}}}
@Composable private fun RadarScreen(){val modules=listOf(RadarModule("9AM","08:30~09:00 급등 후보 탐지","분석중","TOP5 프로파일 연구 연결 예정"),RadarModule("Daily Surge","일중 +5~20% 급등 조기 탐지","연구중","4분할 전체 KRW 역추적 실행"),RadarModule("Accumulation","가격보다 먼저 들어오는 거래대금 탐지","연구중","역추적 결과로 기준 확정 예정"),RadarModule("Wonyotti","캔들+거래량 유사 패턴 탐색","백테스트중","Upbit BTC/KRW 버전"),RadarModule("SWING10","구조적 손절선 기준","보류","단독 성능 부족 · 진입필터 필요"));LazyColumn(Modifier.fillMaxSize().statusBarsPadding().padding(horizontal=14.dp),contentPadding=PaddingValues(top=14.dp,bottom=24.dp),verticalArrangement=Arrangement.spacedBy(10.dp)){item{Header("레이더","전략별 상태와 근거를 한 화면에서 확인")};modules.forEach{m->item{Card(colors=CardDefaults.cardColors(containerColor=Surface),shape=RoundedCornerShape(18.dp)){Column(Modifier.padding(16.dp),verticalArrangement=Arrangement.spacedBy(6.dp)){Row(Modifier.fillMaxWidth(),horizontalArrangement=Arrangement.SpaceBetween){Text(m.name,fontWeight=FontWeight.ExtraBold,fontSize=20.sp);StatusBadge(m.state)};Text(m.subtitle,color=Muted);HorizontalDivider(color=Color(0xFF273142));Text(m.detail,fontSize=13.sp)}}}}}}
@Composable private fun ChartScreen(){LazyColumn(Modifier.fillMaxSize().statusBarsPadding().padding(horizontal=14.dp),contentPadding=PaddingValues(top=14.dp,bottom=24.dp),verticalArrangement=Arrangement.spacedBy(12.dp)){item{Header("차트","가격보다 먼저 움직이는 자금 흐름을 표시할 영역")};item{Card(colors=CardDefaults.cardColors(containerColor=Surface),shape=RoundedCornerShape(20.dp)){Column(Modifier.padding(18.dp),verticalArrangement=Arrangement.spacedBy(10.dp)){Text("BTC / KRW",fontWeight=FontWeight.ExtraBold,fontSize=22.sp);Box(Modifier.fillMaxWidth().height(220.dp).background(Surface2,RoundedCornerShape(14.dp)),contentAlignment=Alignment.Center){Text("실시간 차트 + 자금유입 마커 연결 예정",color=Muted)};Row(horizontalArrangement=Arrangement.spacedBy(6.dp)){listOf("5분","15분","1시간","4시간").forEach{AssistChip(onClick={},label={Text(it)})}}}}};item{OpportunityCard("표시 예정","✓ 초기 · ✓✓ 추가 · S SUPER SIGNAL","UI 준비",Accent)}}}
@Composable private fun AssetScreen(){LazyColumn(Modifier.fillMaxSize().statusBarsPadding().padding(horizontal=14.dp),contentPadding=PaddingValues(top=14.dp,bottom=24.dp),verticalArrangement=Arrangement.spacedBy(10.dp)){item{Header("자산","코인뿐 아니라 금·ETF·예금까지 한곳에서 비교")};item{AssetCard("금","국내/국제 금 시세 · 변동성 · 매수 관심구간")};item{AssetCard("ETF","관심 ETF 수익률 · 변동성 · 자금유입")};item{AssetCard("예금·적금","금리 비교 · 만기 · 실수령액")};item{AssetCard("자산금고","보유자산을 한 화면에서 관리하는 영역")}}}
@Composable private fun AlertScreen(){LazyColumn(Modifier.fillMaxSize().statusBarsPadding().padding(horizontal=14.dp),contentPadding=PaddingValues(top=14.dp,bottom=24.dp),verticalArrangement=Arrangement.spacedBy(10.dp)){item{Header("알림","신호 단계별 알림을 따로 관리")};item{AlertSettingsCard()};item{AlertCard("대기","자금유입 증가 감지","가격은 아직 크게 움직이지 않음")};item{AlertCard("PRE-BLUE","거래대금 재가속","조건 일부 충족 · 진입 아님")};item{AlertCard("BLUE","후보 신호 확인","GREEN 조건 대기")};item{AlertCard("GREEN","검증된 전략에서만 알림","자동주문이 아닌 사용자 확인용")}}}
@Composable private fun MarketChip(title:String,value:String,modifier:Modifier=Modifier){Card(modifier=modifier,colors=CardDefaults.cardColors(containerColor=Surface),shape=RoundedCornerShape(14.dp)){Column(Modifier.padding(10.dp)){Text(title,fontWeight=FontWeight.Bold);Text(value,color=Muted,fontSize=10.sp,maxLines=1)}}}
@Composable private fun OpportunityCard(title:String,body:String,state:String,accent:Color){Card(colors=CardDefaults.cardColors(containerColor=Surface),shape=RoundedCornerShape(18.dp)){Row(Modifier.fillMaxWidth().padding(16.dp),horizontalArrangement=Arrangement.SpaceBetween){Column(Modifier.weight(1f),verticalArrangement=Arrangement.spacedBy(5.dp)){Text(title,fontWeight=FontWeight.Bold,fontSize=18.sp);Text(body,color=Muted,fontSize=13.sp)};Spacer(Modifier.width(10.dp));androidx.compose.material3.Surface(color=accent.copy(alpha=.15f),shape=RoundedCornerShape(50)){Text(state,color=accent,fontWeight=FontWeight.Bold,fontSize=11.sp,modifier=Modifier.padding(horizontal=10.dp,vertical=6.dp))}}}}
@Composable private fun AssetCard(title:String,body:String){Card(colors=CardDefaults.cardColors(containerColor=Surface),shape=RoundedCornerShape(18.dp)){Column(Modifier.padding(16.dp),verticalArrangement=Arrangement.spacedBy(5.dp)){Text(title,fontWeight=FontWeight.ExtraBold,fontSize=20.sp);Text(body,color=Muted,fontSize=13.sp);Text("데이터 연결 준비",color=Accent,fontWeight=FontWeight.Bold,fontSize=12.sp)}}}
@Composable private fun AlertCard(state:String,title:String,detail:String){val c=when(state){"GREEN"->Green;"BLUE"->Color(0xFF55C2FF);"PRE-BLUE"->Accent;else->Amber};Card(colors=CardDefaults.cardColors(containerColor=Surface),shape=RoundedCornerShape(18.dp)){Row(Modifier.fillMaxWidth().padding(16.dp),horizontalArrangement=Arrangement.spacedBy(12.dp)){androidx.compose.material3.Surface(color=c.copy(alpha=.15f),shape=RoundedCornerShape(12.dp)){Text(state,color=c,fontWeight=FontWeight.ExtraBold,modifier=Modifier.padding(horizontal=10.dp,vertical=8.dp))};Column{Text(title,fontWeight=FontWeight.Bold);Text(detail,color=Muted,fontSize=12.sp)}}}}
@Composable private fun SectionTitle(title:String){Text(title,fontSize=20.sp,fontWeight=FontWeight.ExtraBold)}
@Composable private fun StatusBadge(state:String){val c=when(state){"연구완료"->Green;"보류"->Red;"백테스트중","분석중","연구중"->Amber;else->Muted};androidx.compose.material3.Surface(color=c.copy(alpha=.15f),shape=RoundedCornerShape(50)){Text(state,color=c,fontWeight=FontWeight.Bold,fontSize=11.sp,modifier=Modifier.padding(horizontal=10.dp,vertical=5.dp))}}
