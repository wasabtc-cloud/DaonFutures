package com.daon.futures

object TradingEngine {
    fun ema(values: List<Double>, period: Int): Double { if (values.isEmpty()) return 0.0; val k=2.0/(period+1); var e=values.take(period).average(); for(i in period until values.size)e=values[i]*k+e*(1-k); return e }
    fun rsi(values: List<Double>, period: Int=14): Double { if(values.size<=period)return 50.0; var gain=0.0;var loss=0.0;for(i in 1..period){val d=values[i]-values[i-1];if(d>=0)gain+=d else loss-=d};gain/=period;loss/=period;for(i in period+1 until values.size){val d=values[i]-values[i-1];gain=(gain*(period-1)+(if(d>0)d else 0.0))/period;loss=(loss*(period-1)+(if(d<0)-d else 0.0))/period};return if(loss==0.0)100.0 else 100.0-(100.0/(1.0+gain/loss)) }
    fun signal(c15: List<Candle>, c1h: List<Candle>, c4h: List<Candle>, slPct: Double, tpPct: Double): Signal? {
        if(c15.size<55||c1h.size<55||c4h.size<55)return null
        val p15=c15.map{it.close};val p1=c1h.map{it.close};val p4=c4h.map{it.close};val e15=ema(p15,20);val e1f=ema(p1,20);val e1s=ema(p1,50);val e4f=ema(p4,20);val e4s=ema(p4,50);val r=rsi(p15);val prev=c15[c15.size-2];val last=c15.last()
        val longPull=prev.low<=ema(p15.dropLast(1),20)&&last.close>e15;val shortPull=prev.high>=ema(p15.dropLast(1),20)&&last.close<e15
        val long=e4f>e4s&&e1f>e1s&&longPull&&r>=50;val short=e4f<e4s&&e1f<e1s&&shortPull&&r<=50
        return when{long->Signal("LONG",last.close,last.close*(1-slPct/100),last.close*(1+tpPct/100),r,"4H 상승 + 1H 상승 + 15M 눌림 + RSI",last.closeTime);short->Signal("SHORT",last.close,last.close*(1+slPct/100),last.close*(1-tpPct/100),r,"4H 하락 + 1H 하락 + 15M 반등 + RSI",last.closeTime);else->null}
    }
}
