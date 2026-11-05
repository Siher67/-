import streamlit as st
import pandas as pd
import plotly.express as px
import yfinance as yf
from fredapi import Fred
from google import genai # 👈 引入 Google GenAI SDK

# 頁面基本配置
st.set_page_config(page_title="總體經濟與金融即時儀表板", layout="wide")
st.title("🌐 全球總體經濟與金融指標即時儀表板")

# 側邊欄：輸入 API Key 與刷新控制
st.sidebar.header("⚙️ 設定與金鑰")

# 1. FRED API Key 讀取邏輯
if "FRED_API_KEY" in st.secrets:
    fred_key = st.secrets["FRED_API_KEY"]
    st.sidebar.success("✅ 已自動讀取 FRED API Key！")
else:
    fred_key = st.sidebar.text_input("請輸入你的 FRED API Key:", type="password")

# 2. Gemini API Key 讀取邏輯
if "GEMINI_API_KEY" in st.secrets:
    gemini_key = st.secrets["GEMINI_API_KEY"]
    st.sidebar.success("✅ 已自動讀取 Gemini API Key！")
else:
    gemini_key = st.sidebar.text_input("請輸入你的 Gemini API Key:", type="password")

if st.sidebar.button("手動刷新數據"):
    st.cache_data.clear()

# ================= 數據抓取區塊 =================
@st.cache_data(ttl=3600)
def get_fred_data(api_key):
    fred = Fred(api_key=api_key)
    data = {
        "CPI 物價指數": fred.get_series("CPIAUCSL"),
        "10年期美債殖利率": fred.get_series("DGS10"),
        "2年期美債殖利率": fred.get_series("DGS2"),
        "美國失業率": fred.get_series("UNRATE"),
        "聯邦基金利率": fred.get_series("FEDFUNDS"),
        "日本10年期公債殖利率": fred.get_series("IRLTLT01JPM156N")
    }
    df = pd.DataFrame(data).ffill().tail(365)
    df["10年與2年美債利差"] = df["10年期美債殖利率"] - df["2年期美債殖利率"]
    return df

@st.cache_data(ttl=600)
def get_market_data():
    tickers = {
        "S&P 500": "^GSPC",
        "台灣加權指數": "^TWII",
        "布蘭特原油": "BZ=F",
        "美元/台幣匯率": "TWD=X",
        "黃金期貨/現貨": "GC=F"
    }
    df = yf.download(list(tickers.values()), period="1y")["Close"]
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = df.columns.get_level_values(0)
    df.rename(columns={v: k for k, v in tickers.items()}, inplace=True)
    return df

# ================= 頁面渲染邏輯 =================
if fred_key:
    try:
        macro_df = get_fred_data(fred_key)
        market_df = get_market_data()

        # --- 第一區塊：核心 KPI 卡片 ---
        st.subheader("📊 關鍵總體經濟指標 (FRED)")
        col1, col2, col3, col4, col5 = st.columns(5)
        
        latest_cpi = macro_df["CPI 物價指數"].dropna().iloc[-1]
        col1.metric("CPI 物價指數", f"{latest_cpi:.1f}")
        
        valid_us_rates = macro_df["10年期美債殖利率"].dropna()
        latest_us_rate = valid_us_rates.iloc[-1]
        us_rate_prev = valid_us_rates.iloc[-2] if len(valid_us_rates) > 1 else latest_us_rate
        col2.metric("10年美債殖利率", f"{latest_us_rate:.2f}%", f"{latest_us_rate - us_rate_prev:+.2f}%")
        
        latest_unemp = macro_df["美國失業率"].dropna().iloc[-1]
        col3.metric("美國失業率", f"{latest_unemp:.1f}%")
        
        latest_fed = macro_df["聯邦基金利率"].dropna().iloc[-1]
        col4.metric("聯邦基金利率", f"{latest_fed:.2f}%")
        
        valid_jp_rates = macro_df["日本10年期公債殖利率"].dropna()
        if not valid_jp_rates.empty:
            latest_jp_rate = valid_jp_rates.iloc[-1]
            jp_rate_prev = valid_jp_rates.iloc[-2] if len(valid_jp_rates) > 1 else latest_jp_rate
            col5.metric("日本10年公債殖利率", f"{latest_jp_rate:.2f}%", f"{latest_jp_rate - jp_rate_prev:+.2f}%")

        # --- 第二區塊：經濟衰退指標監控 ---
        st.write("---")
        st.subheader("🚨 經濟衰退指標：10年期與2年期美債利差")
        valid_spreads = macro_df["10年與2年美債利差"].dropna()
        latest_spread = valid_spreads.iloc[-1] if not valid_spreads.empty else 0
        
        if not valid_spreads.empty:
            if latest_spread < 0:
                st.error(f"⚠️ 目前利差為 **{latest_spread:.2f}%**。殖利率曲線出現倒掛 (利差小於 0)，市場預期未來可能有經濟衰退風險！")
            else:
                st.success(f"✅ 目前利差為 **{latest_spread:.2f}%**。殖利率曲線正常 (利差大於 0)。")
            
            fig_spread = px.line(valid_spreads, title="美債利差近一年走勢 (10年期減2年期)")
            fig_spread.add_hline(y=0, line_dash="dash", line_color="red", annotation_text="倒掛警戒線", annotation_position="bottom right")
            st.plotly_chart(fig_spread, use_container_width=True)

        # --- 第三區塊：互動式圖表 ---
        st.write("---")
        st.subheader("📈 市場走勢與總體指標折線圖")
        tab1, tab2 = st.tabs(["金融市場走勢 (yfinance)", "總體經濟趨勢 (FRED)"])
        
        with tab1:
            market_choice = st.selectbox("選擇金融市場標的：", market_df.columns)
            fig1 = px.line(market_df, y=market_choice, title=f"{market_choice} 近一年走勢")
            st.plotly_chart(fig1, use_container_width=True)
            
        with tab2:
            macro_choice = st.selectbox("選擇總體經濟指標：", macro_df.columns)
            fig2 = px.line(macro_df, y=macro_choice, title=f"{macro_choice} 近一年走勢")
            st.plotly_chart(fig2, use_container_width=True)

        # --- 第四區塊：AI 總體經濟摘要 ---
        st.write("---")
        st.subheader("🤖 AI 總體經濟摘要分析")
        st.write("結合最新 FRED 數據，讓 Gemini 為您產生即時短評。")
        
        if st.button("產生 AI 總體經濟摘要", type="primary"):
            if not gemini_key:
                st.warning("請先在左側欄位輸入您的 Gemini API Key！")
            else:
                # 定義給 AI 的 Prompt，注入最新獲取的變數
                prompt = f"""
                身為一位專業的華爾街總體經濟分析師，請根據以下最新美國總體經濟數據，
                撰寫一份約 200 字的總體經濟短評。請綜合分析通膨、就業與利率的現況，
                並推測對未來經濟與市場可能的影響（例如是否軟著陸或衰退風險）。
                
                最新總經數據：
                - CPI 物價指數：{latest_cpi:.1f}
                - 失業率：{latest_unemp:.1f}%
                - 聯邦基金利率：{latest_fed:.2f}%
                - 10年與2年美債利差：{latest_spread:.2f}%
                """
                
                # 使用 st.spinner 顯示載入動畫
                with st.spinner("Gemini 正在分析最新總經數據，請稍候..."):
                    try:
                        # 呼叫 google-genai 介面
                        client = genai.Client(api_key=gemini_key)
                        response = client.models.generate_content(
                            model="gemini-2.5-flash",
                            contents=prompt
                        )
                        # 將 AI 產生的文字印出
                        st.info(response.text)
                    except Exception as e:
                        st.error(f"AI 生成失敗，請確認 API Key 是否正確。錯誤訊息：{e}")

    except Exception as e:
        st.error(f"數據讀取失敗，請確認 API Key 或網路狀態。錯誤訊息: {e}")
else:
    st.info("👈 請在左側輸入您的 FRED API Key 以開啟儀表板。")
