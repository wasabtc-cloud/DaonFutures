package com.daon.futures

import android.app.NotificationChannel
import android.app.NotificationManager
import android.content.Context
import android.os.Build
import androidx.core.app.NotificationCompat
import androidx.glance.appwidget.updateAll
import androidx.work.CoroutineWorker
import androidx.work.WorkerParameters
import com.daon.futures.widget.DaonWidget
import java.text.SimpleDateFormat
import java.util.Date
import java.util.Locale

class SignalWorker(ctx: Context, params: WorkerParameters): CoroutineWorker(ctx,params){
    override suspend fun doWork(): Result = try {
        val p=AppStore.prefs(applicationContext);val risk=AppStore.riskStatus(applicationContext)
        if(risk.locked){DaonWidget().updateAll(applicationContext);return Result.success()}
        val symbol=p.getString("symbol","BTCUSDT")!!;val sl=p.getFloat("sl",1f).toDouble();val tp=p.getFloat("tp",1.5f).toDouble();val s=BinanceApi.analyze(symbol,sl,tp)
        if(s!=null){val signalKey="$symbol:${s.side}:${(s.candleTime/900000L)}";val notified=p.getString("last_notified_key","");p.edit().putString("last_symbol",symbol).putString("last_side",s.side).putString("last_price",fmt(s.price)).putString("last_sl",fmt(s.sl)).putString("last_tp",fmt(s.tp)).putString("last_rsi",String.format(Locale.US,"%.1f",s.rsi)).putString("last_reason",s.reason).putLong("last_candle",s.candleTime).putString("last_updated",fmtDate(s.candleTime)).apply();if(notified!=signalKey){AppStore.addHistory(applicationContext,s,symbol);if(p.getBoolean("notifications",true))notifySignal(s,symbol);p.edit().putString("last_notified_key",signalKey).apply()}}
        else p.edit().putString("last_side","WAIT").putString("last_updated",fmtDate(System.currentTimeMillis())).apply()
        DaonWidget().updateAll(applicationContext);Result.success()
    }catch(_:Exception){Result.retry()}
    private fun notifySignal(s:Signal,symbol:String){val nm=applicationContext.getSystemService(Context.NOTIFICATION_SERVICE) as NotificationManager;if(Build.VERSION.SDK_INT>=26)nm.createNotificationChannel(NotificationChannel("signals","매매 신호",NotificationManager.IMPORTANCE_HIGH));val title=if(s.side=="LONG")"🟢 $symbol LONG 신호" else "🔴 $symbol SHORT 신호";val text="진입 ${fmt(s.price)} · SL ${fmt(s.sl)} · TP ${fmt(s.tp)} · RSI ${"%.1f".format(s.rsi)}";nm.notify((System.currentTimeMillis()%100000).toInt(),NotificationCompat.Builder(applicationContext,"signals").setSmallIcon(android.R.drawable.ic_dialog_info).setContentTitle(title).setContentText(text).setStyle(NotificationCompat.BigTextStyle().bigText("$text\n${s.reason}")).setAutoCancel(true).build())}
    private fun fmt(v:Double)=String.format(Locale.KOREA,"%,.2f",v)
    private fun fmtDate(v:Long)=SimpleDateFormat("MM/dd HH:mm",Locale.KOREA).format(Date(v))
}
