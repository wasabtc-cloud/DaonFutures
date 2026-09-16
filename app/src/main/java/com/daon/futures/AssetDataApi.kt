package com.daon.futures

import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext
import okhttp3.OkHttpClient
import okhttp3.Request
import org.json.JSONObject
import java.net.URLEncoder

/** Official-data connectors for Catch World asset screens.
 * Keys are injected at build time; never hard-code credentials in source.
 */
object AssetDataApi {
    private val http = OkHttpClient()

    data class GoldQuote(val name:String,val price:String,val changePct:String,val date:String)
    data class EtfQuote(val name:String,val code:String,val price:String,val changePct:String,val volume:String,val date:String)
    data class Deposit(val company:String,val product:String,val rate:String,val maxRate:String,val joinWay:String)

    private fun get(url:String):String {
        val r=http.newCall(Request.Builder().url(url).get().build()).execute()
        if(!r.isSuccessful) error("HTTP ${r.code}")
        return r.body?.string() ?: error("empty response")
    }
    private fun enc(v:String)=URLEncoder.encode(v,"UTF-8")

    suspend fun gold():Result<List<GoldQuote>> = withContext(Dispatchers.IO){ runCatching {
        require(BuildConfig.PUBLIC_DATA_KEY.isNotBlank()){"공공데이터 API 키가 필요합니다"}
        val url="https://apis.data.go.kr/1160100/service/GetGeneralProductInfoService/getGoldPriceInfo?serviceKey=${enc(BuildConfig.PUBLIC_DATA_KEY)}&numOfRows=20&pageNo=1&resultType=json"
        val root=JSONObject(get(url)); val arr=root.getJSONObject("response").getJSONObject("body").getJSONObject("items").getJSONArray("item")
        (0 until arr.length()).map{i->val x=arr.getJSONObject(i);GoldQuote(x.optString("itmsNm","KRX 금"),x.optString("clpr","-"),x.optString("fltRt","-"),x.optString("basDt","-"))}
    }}

    suspend fun etfs():Result<List<EtfQuote>> = withContext(Dispatchers.IO){ runCatching {
        require(BuildConfig.PUBLIC_DATA_KEY.isNotBlank()){"공공데이터 API 키가 필요합니다"}
        val url="https://apis.data.go.kr/1160100/service/GetSecuritiesProductInfoService/getETFPriceInfo?serviceKey=${enc(BuildConfig.PUBLIC_DATA_KEY)}&numOfRows=100&pageNo=1&resultType=json"
        val root=JSONObject(get(url)); val arr=root.getJSONObject("response").getJSONObject("body").getJSONObject("items").getJSONArray("item")
        (0 until arr.length()).map{i->val x=arr.getJSONObject(i);EtfQuote(x.optString("itmsNm","-"),x.optString("srtnCd","-"),x.optString("clpr","-"),x.optString("fltRt","-"),x.optString("trqu","-"),x.optString("basDt","-"))}
    }}

    suspend fun deposits():Result<List<Deposit>> = withContext(Dispatchers.IO){ runCatching {
        require(BuildConfig.FINLIFE_KEY.isNotBlank()){"금융상품 한눈에 API 키가 필요합니다"}
        val url="https://finlife.fss.or.kr/finlifeapi/depositProductsSearch.json?auth=${enc(BuildConfig.FINLIFE_KEY)}&topFinGrpNo=020000&pageNo=1"
        val root=JSONObject(get(url)).getJSONObject("result")
        val base=root.getJSONArray("baseList"); val options=root.getJSONArray("optionList")
        val rates=mutableMapOf<String,Pair<Double,Double>>()
        for(i in 0 until options.length()){val x=options.getJSONObject(i);val key=x.optString("fin_prdt_cd");val r=x.optDouble("intr_rate",Double.NaN);val m=x.optDouble("intr_rate2",Double.NaN);val old=rates[key]?:Pair(Double.NaN,Double.NaN);rates[key]=Pair(listOf(old.first,r).filter{!it.isNaN()}.maxOrNull()?:Double.NaN,listOf(old.second,m).filter{!it.isNaN()}.maxOrNull()?:Double.NaN)}
        (0 until base.length()).map{i->val x=base.getJSONObject(i);val rr=rates[x.optString("fin_prdt_cd")];Deposit(x.optString("kor_co_nm","-"),x.optString("fin_prdt_nm","-"),rr?.first?.takeIf{!it.isNaN()}?.toString()?:"-",rr?.second?.takeIf{!it.isNaN()}?.toString()?:"-",x.optString("join_way","-"))}
    }}
}