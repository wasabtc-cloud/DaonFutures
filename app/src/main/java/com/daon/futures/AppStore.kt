package com.daon.futures

import android.content.Context
import org.json.JSONArray
import org.json.JSONObject
import java.text.SimpleDateFormat
import java.util.Date
import java.util.Locale

object AppStore {
    private const val PREF="settings"
    private const val DAY_FMT="yyyy-MM-dd"
    fun prefs(c:Context)=c.getSharedPreferences(PREF,0)
    fun saveSettings(c:Context,symbol:String,sl:Float,tp:Float,lev:Int,notifications:Boolean){prefs(c).edit().putString("symbol",symbol).putFloat("sl",sl).putFloat("tp",tp).putInt("lev",lev).putBoolean("notifications",notifications).apply()}
    fun addHistory(c:Context,s:Signal,symbol:String){val p=prefs(c);val old=JSONArray(p.getString("history","[]"));val out=JSONArray();val item=JSONObject().apply{put("symbol",symbol);put("side",s.side);put("price",s.price);put("sl",s.sl);put("tp",s.tp);put("rsi",s.rsi);put("timestamp",s.candleTime)};out.put(item);for(i in 0 until minOf(old.length(),19))out.put(old.getJSONObject(i));p.edit().putString("history",out.toString()).apply()}
    fun history(c:Context):List<SignalRecord>{val a=JSONArray(prefs(c).getString("history","[]"));return (0 until a.length()).map{val o=a.getJSONObject(it);SignalRecord(o.getString("symbol"),o.getString("side"),o.getDouble("price"),o.getDouble("sl"),o.getDouble("tp"),o.getDouble("rsi"),o.getLong("timestamp"))}}
    fun dayKey():String=SimpleDateFormat(DAY_FMT,Locale.KOREA).format(Date())
    private fun ensureDay(c:Context){val p=prefs(c);val key=dayKey();if(p.getString("risk_day","")!=key){p.edit().putString("risk_day",key).putInt("daily_pnl",0).putInt("consecutive_losses",0).putBoolean("daily_locked",false).apply()}}
    data class RiskStatus(val pnl:Int,val consecutiveLosses:Int,val locked:Boolean)
    fun riskStatus(c:Context):RiskStatus{ensureDay(c);val p=prefs(c);return RiskStatus(p.getInt("daily_pnl",0),p.getInt("consecutive_losses",0),p.getBoolean("daily_locked",false))}
    fun recordResult(c:Context,won:Boolean,amountWonOrLost:Int,maxDailyLoss:Int=20000,lossStreakLimit:Int=2):RiskStatus{ensureDay(c);val p=prefs(c);val signed=if(won)kotlin.math.abs(amountWonOrLost) else -kotlin.math.abs(amountWonOrLost);val pnl=p.getInt("daily_pnl",0)+signed;val streak=if(won)0 else p.getInt("consecutive_losses",0)+1;val locked=pnl<=-maxDailyLoss || streak>=lossStreakLimit;p.edit().putInt("daily_pnl",pnl).putInt("consecutive_losses",streak).putBoolean("daily_locked",locked).apply();return RiskStatus(pnl,streak,locked)}
    fun resetRisk(c:Context){ensureDay(c);prefs(c).edit().putInt("daily_pnl",0).putInt("consecutive_losses",0).putBoolean("daily_locked",false).apply()}
}
