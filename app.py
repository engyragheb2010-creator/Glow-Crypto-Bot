import streamlit as st
import ccxt
import numpy as np
import pandas as pd
import time
import json
import os

st.set_page_config(page_title="Glow Pro Simple Bot", page_icon="⚡", layout="wide")
st.title("⚡ تطبيق التوصيات (استراتيجية الثنائي السريع: EMA + MACD)")

API_KEY = "41e8e6d1-3d2d-4861-b0df-61ccdb79e34b"
SECRET_KEY = "1FC2FDF62E1F188458144B7700759BC3" 
PASSPHRASE = 'Ahmedengy2010@'

@st.cache_resource
def get_exchange():
    return ccxt.okx({'enableRateLimit': True})

exchange = get_exchange()

def load_portfolio():
    if os.path.exists("portfolio.json"):
        try:
            with open("portfolio.json", "r") as f: return json.load(f)
        except: return []
    return []

def save_portfolio(trades):
    with open("portfolio.json", "w") as f: json.dump(trades, f)

if 'scalping_opps' not in st.session_state: st.session_state.scalping_opps = []
if 'tracked_trades' not in st.session_state: st.session_state.tracked_trades = load_portfolio()

def calculate_macd(prices):
    exp1 = pd.Series(prices).ewm(span=12, adjust=False).mean()
    exp2 = pd.Series(prices).ewm(span=26, adjust=False).mean()
    macd = exp1 - exp2
    signal = macd.ewm(span=9, adjust=False).mean()
    return macd.iloc[-1], signal.iloc[-1]

def calculate_ema_series(prices, period):
    return pd.Series(prices).ewm(span=period, adjust=False).mean()

def calculate_atr(highs, lows, closes, period=14):
    tr_list = [highs[0] - lows[0]]
    for i in range(1, len(closes)):
        h_l = highs[i] - lows[i]
        h_pc = abs(highs[i] - closes[i-1])
        l_pc = abs(lows[i] - closes[i-1])
        tr_list.append(max(h_l, h_pc, l_pc))
    atr = pd.Series(tr_list).rolling(window=period).mean().iloc[-1]
    return atr if not np.isnan(atr) else (highs[-1] * 0.01)

def play_audio_alert():
    audio_html = """
        <audio autoplay>
          <source src="https://assets.mixkit.co/active_storage/sfx/2869/2869-preview.mp3" type="audio/mp3">
        </audio>
    """
    st.markdown(audio_html, unsafe_allow_html=True)

def track_trade(opp, trade_type):
    for t in st.session_state.tracked_trades:
        if t['symbol'] == opp['symbol'] and t['status'] in ['⏳ معلقة', '🟢 نشطة']:
            st.toast(f"الصفقة موجودة بالفعل!")
            return
    new_trade = {
        'id': f"{opp['symbol']}_{time.time()}", 'symbol': opp['symbol'], 'type': trade_type,
        'direction': opp.get('direction', '🟢 LONG'), 'entry': opp['buy'], 'tp': opp['tp'],
        'sl': opp['sl'], 'status': '⏳ معلقة'
    }
    st.session_state.tracked_trades.append(new_trade)
    save_portfolio(st.session_state.tracked_trades)
    st.toast(f"تمت الإضافة بنجاح للمحفظة الدائمة!")

col1, col2 = st.columns([3, 1])
with col1:
    if st.button('🚀 فحص سريع (EMA + MACD)'):
        with st.spinner('جاري فحص التقاطعات وزخم الـ MACD على فريم 5 دقائق...'):
            symbols = ['BTC/USDT', 'ETH/USDT', 'SOL/USDT', 'DOGE/USDT']
            all_opps = []
            
            for symbol in symbols:
                try:
                    ohlcv = exchange.fetch_ohlcv(symbol, '5m', limit=100)
                    h = np.array([c[2] for c in ohlcv])
                    l = np.array([c[3] for c in ohlcv])
                    c = np.array([c[4] for c in ohlcv])
                    curr = c[-1]
                    
                    ema5 = calculate_ema_series(c, 5)
                    ema13 = calculate_ema_series(c, 13)
                    macd, macd_signal = calculate_macd(c)
                    atr = calculate_atr(h, l, c, 14)
                    
                    # الشرطين الأساسيين فقط: تقاطع EMA + توافق الـ MACD
                    long_cross = (ema5.iloc[-2] <= ema13.iloc[-2]) and (ema5.iloc[-1] > ema13.iloc[-1])
                    short_cross = (ema5.iloc[-2] >= ema13.iloc[-2]) and (ema5.iloc[-1] < ema13.iloc[-1])
                    
                    score = 0
                    direction = ""
                    
                    if long_cross and macd > macd_signal:
                        score = 90
                        direction = '🟢 LONG (EMA+MACD)'
                        tp = curr + (2.0 * atr)
                        sl = curr - (1.0 * atr)
                    elif short_cross and macd < macd_signal:
                        score = 90
                        direction = '🔴 SHORT (EMA+MACD)'
                        tp = curr - (2.0 * atr)
                        sl = curr + (1.0 * atr)
                    else:
                        continue
                        
                    all_opps.append({
                        'symbol': symbol, 'direction': direction, 'price': curr, 'score': score,
                        'buy': round(curr, 4), 'tp': round(tp, 4), 'sl': round(sl, 4)
                    })
                except: continue
                    
            st.session_state.scalping_opps = all_opps
            if all_opps:
                play_audio_alert()

with col2:
    if st.button('🔄 تحديث المحفظة'):
        with st.spinner('تحديث...'):
            for t in st.session_state.tracked_trades:
                if t['status'] in ['⏳ معلقة', '🟢 نشطة']:
                    try:
                        ticker = exchange.fetch_ticker(t['symbol'])
                        curr = ticker['last']
                        is_long = 'LONG' in t['direction']
                        if t['status'] == '⏳ معلقة':
                            if (is_long and curr <= t['entry']) or (not is_long and curr >= t['entry']): t['status'] = '🟢 نشطة'
                        if t['status'] == '🟢 نشطة':
                            if is_long:
                                if curr >= t['tp']: t['status'] = '🎯 ربح (Hit TP)'
                                elif curr <= t['sl']: t['status'] = '🛑 خسارة (Hit SL)'
                            else:
                                if curr <= t['tp']: t['status'] = '🎯 ربح (Hit TP)'
                                elif curr >= t['sl']: t['status'] = '🛑 خسارة (Hit SL)'
                    except: pass
            save_portfolio(st.session_state.tracked_trades)
        st.success("تم التحديث!")
        
    st.markdown("---")
    if st.button('🧹 مسح الصفقات المغلقة'):
        st.session_state.tracked_trades = [t for t in st.session_state.tracked_trades if t['status'] not in ['🎯 ربح (Hit TP)', '🛑 خسارة (Hit SL)']]
        save_portfolio(st.session_state.tracked_trades)
        st.success("تم تنظيف المحفظة!")
        
    if st.button('🧨 تصفير المحفظة بالكامل'):
        st.session_state.tracked_trades = []
        save_portfolio([])
        st.success("تم مسح كل الصفقات!")

tab3, tab4 = st.tabs(["⏱️ Scalping (الثنائي السريع)", "💼 محفظتي (دائمة)"])

with tab3:
    st.info("⚡ البوت يعتمد الآن حصرياً على تقاطع الـ (EMA 5/13) مع عزم الـ (MACD) على فريم الـ 5 دقائق.")
    if not st.session_state.scalping_opps:
        st.warning("لا توجد تقاطعات مطابقة حالياً. جاري الفحص..")
    else:
        for i, opp in enumerate(st.session_state.scalping_opps, 1):
            st.markdown(f"**{opp['symbol']}** {opp['direction']} (تقييم: {opp['score']}/100 ⭐️) | السعر: {opp['price']} | هدف: `{opp['tp']}` | وقف: `{opp['sl']}`")
            if st.button(f"➕ تتبع", key=f"sc_{i}_{opp['symbol']}"): track_trade(opp, 'Scalping')
with tab4:
    if not st.session_state.tracked_trades: st.warning("المحفظة فارغة.")
    else:
        for t in reversed(st.session_state.tracked_trades):
            status_icon = "⚪"
            if "نشطة" in t['status']: status_icon = "🟢"
            elif "ربح" in t['status']: status_icon = "🎯"
            elif "خسارة" in t['status']: status_icon = "🛑"
            st.markdown(f"**{t['symbol']}** | {t['type']} | {t['direction']} | {status_icon} **{t['status']}**")
            st.markdown(f"دخول: {t['entry']} | هدف: {t['tp']} | وقف: {t['sl']}")
            st.markdown("---")

