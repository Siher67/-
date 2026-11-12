import streamlit as st
import pandas as pd
import plotly.express as px
import yfinance as yf
from fredapi import Fred
import feedparser
import google.generativeai as genai
from urllib.parse import quote  # 解決 URL 空白字元轉碼問題

# ==========================================
# 1. 頁面配置與側邊欄金鑰設定
# ==========================================
st.set_page_config(page_title="總體經濟、金融與 NLP 市場情緒儀表板", layout="wide")
st.title("🌐 總體經濟、金融指標與 AI 輿論情緒即時儀表板")

st.sidebar.header("⚙️ 設定與金鑰")

# 1.1 檢查 FRED API Key
if "FRED_API_KEY" in st.secrets:
    fred_key = st.secrets["FRED_API_KEY"]
    st.sidebar.success("已自動讀取 FRED API Key！")
else:
    fred_key = st.sidebar.text_input("請輸入 FRED API Key:", type="password")

# 1.2 檢查 Gemini API Key (NLP 情緒分析用)
gemini_key = None
if "GEMINI_API_KEY" in st.secrets:
    gemini_key = st.secrets["GEMINI_API_KEY"]
    genai.configure(api_key=gemini_key)
    st.sidebar.success("已自動讀取 Gemini API Key！")
else:
    gemini_input = st.sidebar.text_input("請輸入 Gemini API Key (情緒分析用):", type="password")
    if gemini_input:
        gemini_key = gemini_input
        genai.configure(api_key=gemini_key)

if st.sidebar.button("手動刷新數據"):
    st.cache_data.clear()

# ==========================================
# 2. 數據抓取函式 (FRED, yfinance, RSS 新聞)
# ==========================================
@st.cache_data(ttl=3600)
def get_fred_data(api_key):
    fred = Fred(api_key=api_key)
    data = {
        "CPI 物價指數": fred.get_series("CPIAUCSL"),
        "10年期美債殖利率": fred.get_series("DGS10"),
        "2年期美債殖利率": fred.get_series("DGS2"),
        "美國失業率": fred.get_series("UNRATE"),
        "聯邦基金利率": fred.get_series("FEDFUNDS")
    }
    # 放大至近 3 年 (約 1095 天)，使殖利率曲線倒掛趨勢更明顯
    df = pd.DataFrame(data).ffill().tail(1095)
    
    # 計算 10Y - 2Y 利差
    df["10Y-2Y利差"] = df["10年期美債殖利率"] - df["2年期美債殖利率"]
    return df

@st.cache_data(ttl=600)
def get_market_data():
    tickers = {
        "S&P 500": "^GSPC",
        "台灣加權指數": "^TWII",
        "布蘭特原油": "BZ=F",
        "美元/台幣匯率": "TWD=X"
    }
    df = yf.download(list(tickers.values()), period="1y")["Close"]
    df.rename(columns={v: k for k, v in tickers.items()}, inplace=True)
    return df

@st.cache_data(ttl=1800)
def fetch_google_news(keyword="Federal Reserve Inflation"):
    safe_keyword = quote(keyword)
    url = f"https://news.google.com/rss/search?q={safe_keyword}&hl=en-US"
    feed = feedparser.parse(url)
    return [entry.title for entry in feed.entries[:8]]

# ==========================================
# 3. 頁面渲染邏輯
# ==========================================
if fred_key:
    try:
        macro_df = get_fred_data(fred_key)
        market_df = get_market_data()

        # --- 殖利率倒掛警示燈號 ---
        latest_spread = macro_df["10Y-2Y利差"].dropna().iloc[-1]
        spread_prev = macro_df["10Y-2Y利差"].dropna().iloc[-2]
        
        if latest_spread < 0:
            st.error(f"⚠️ **警示：殖利率曲線倒掛！** 10 年期與 2 年期美債利差為 **{latest_spread:.2f}%**，暗示市場對未來潛在衰退的擔憂。")
        else:
            st.success(f"✅ **殖利率曲線未倒掛**。目前 10 年期與 2 年期美債利差為 **{latest_spread:.2f}%**。")

        # --- 第一區塊：核心總經 KPI 卡片 ---
        st.subheader("📊 關鍵總體經濟指標 (FRED)")
        col1, col2, col3, col4, col5 = st.columns(5)
        
        latest_cpi = macro_df["CPI 物價指數"].dropna().iloc[-1]
        col1.metric("CPI 物價指數", f"{latest_cpi:.1f}")
        
        latest_rate_10 = macro_df["10年期美債殖利率"].dropna().iloc[-1]
        rate_prev_10 = macro_df["10年期美債殖利率"].dropna().iloc[-2]
        col2.metric("10年美債殖利率", f"{latest_rate_10:.2f}%", f"{latest_rate_10 - rate_prev_10:+.2f}%")
        
        col3.metric("10Y-2Y 利差", f"{latest_spread:.2f}%", f"{latest_spread - spread_prev:+.2f}%")
        
        latest_unemp = macro_df["美國失業率"].dropna().iloc[-1]
        col4.metric("美國失業率", f"{latest_unemp:.1f}%")
        
        latest_fed = macro_df["聯邦基金利率"].dropna().iloc[-1]
        col5.metric("聯邦基金利率", f"{latest_fed:.2f}%")

        st.write("---")

        # --- 第二區塊：分頁儀表板 ---
        tab1, tab2, tab3 = st.tabs([
            "📈 金融市場走勢 (yfinance)", 
            "🏛️ 總體經濟趨勢 (FRED)", 
            "📰 NLP 市場新聞與鷹鴿情緒分析"
        ])
        
        # 頁籤 1: 金融市場
        with tab1:
            market_choice = st.selectbox("選擇金融市場標的：", market_df.columns)
            fig1 = px.line(market_df, y=market_choice, title=f"{market_choice} 近一年走勢")
            st.plotly_chart(fig1, use_container_width=True)
            
        # 頁籤 2: 總體經濟
        with tab2:
            st.markdown("#### 📉 10Y-2Y 殖利率利差走勢")
            fig_spread = px.line(macro_df, y="10Y-2Y利差")
            fig_spread.add_hline(y=0, line_dash="dash", line_color="red", annotation_text="倒掛警戒線 (0%)")
            fig_spread.update_layout(margin=dict(l=20, r=20, t=30, b=20))
            st.plotly_chart(fig_spread, use_container_width=True)
            
            st.write("---")
            
            macro_choice = st.selectbox("選擇其他總體經濟指標：", macro_df.columns)
            fig2 = px.line(macro_df, y=macro_choice, title=f"{macro_choice} 歷史走勢")
            st.plotly_chart(fig2, use_container_width=True)

        # 頁籤 3: NLP 市場新聞與情緒分析
        with tab3:
            st.subheader("📰 即時財經新聞與 LLM 鷹鴿派情緒分析")
            
            search_kw = st.text_input("🔍 輸入新聞關鍵字 (預設: Federal Reserve Inflation):", value="Federal Reserve Inflation")
            news_titles = fetch_google_news(search_kw)

            nlp_col1, nlp_col2 = st.columns([1, 1])

            with nlp_col1:
                st.markdown("### 📌 最新財經新聞標題 (RSS)")
                if news_titles:
                    for i, title in enumerate(news_titles, 1):
                        st.write(f"**{i}.** {title}")
                else:
                    st.warning("查無相關新聞標題，請嘗試更換關鍵字。")

            with nlp_col2:
                st.markdown("### 🤖 Gemini AI 鷹鴿派與情緒打分")
                if gemini_key:
                    if st.button("🚀 開始分析新聞市場情緒", type="primary"):
                        if news_titles:
                            with st.spinner("Gemini 正在剖析文本立場與鷹鴿情緒中..."):
                                try:
                                    news_text = "\n".join([f"- {t}" for t in news_titles])
                                    prompt = f"你是一位專業總體經濟分析師。請分析以下 8 條新聞標題：\n{news_text}\n\n" \
                                             f"請以繁體中文輸出結構化報告：\n" \
                                             f"1. 整體市場情緒分數 (0~100)\n" \
                                             f"2. 貨幣政策立場判定 (鷹派/鴿派/中立)\n" \
                                             f"3. 重點分析與逐條評分表格 (Markdown Format)"
                                    
                                    # ==========================================
                                    # 優化點：動態向 Google API 查詢可用模型，徹底解決 404 問題
                                    # ==========================================
                                    target_model = None
                                    for m in genai.list_models():
                                        if 'generateContent' in m.supported_generation_methods:
                                            # 優先尋找 1.5-flash 模型，若無則降級尋找 pro
                                            if '1.5-flash' in m.name:
                                                target_model = m.name.replace('models/', '')
                                                break
                                            elif 'pro' in m.name:
                                                target_model = m.name.replace('models/', '')
                                    
                                    # 萬一迴圈因權限問題沒找到，給定一個標準預設值
                                    if not target_model:
                                        target_model = "gemini-1.5-flash"
                                        
                                    model = genai.GenerativeModel(target_model)
                                    response = model.generate_content(prompt)
                                    
                                    st.markdown(response.text)
                                    st.caption(f"*(💡 系統自動偵測並調用可用模型: `{target_model}`)*")
                                    
                                except Exception as e:
                                    st.error(f"AI 分析時發生錯誤: {e}")
                                    st.info("建議檢查：1. API Key 是否正確。 2. GitHub 的 requirements.txt 是否已加上 `google-generativeai>=0.5.2`")
                        else:
                            st.warning("尚無新聞數據可供分析。")
                else:
                    st.warning("👈 請在側邊欄輸入 Gemini API Key（或設定在 Secrets 中）以啟用 AI 文本情緒分析功能。")

    except Exception as e:
        st.error(f"數據讀取失敗，請確認 API 狀態。錯誤訊息: {e}")
else:
    st.info("👈 請在左側輸入您的 FRED API Key 以開啟儀表板。")
