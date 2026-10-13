import streamlit as st
import ccxt
import numpy as np
import pandas as pd
import time
import json
import os

st.set_page_config(page_title="Glow Pro Multi-Strategy Bot", page_icon="⚡", layout="wide")
st.title("⚡ تطبيق التوصيات الذكي (السكالبينج + فلتر التريند العام)")

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
if 'trend_opps' not in st.session_state: st.session_state.trend_opps = []
if 'tracked_trades' not in st.session_state: st.session_state.tracked_trades = load_portfolio()

def calculate_rsi(prices, period=14):
    deltas = np.diff(prices)
    if len(deltas) < period + 1: return 50
    seed = deltas[:period+1]
    up = seed[seed >= 0].sum() / period
    down = -seed[seed < 0].sum() / period
    rs = up / down if down != 0 else 0
    rsi = 100. - (100. / (1. + rs))
    for i in range(period, len(deltas)):
        delta = deltas[i]
        if delta > 0:
            up = (up * (period - 1) + delta) / period
            down = (down * (period - 1)) / period
        else:
            up = (up * (period - 1)) / period
            down = (down * (period - 1) - delta) / period
            rs = up / down if down != 0 else 0
            rsi = 100. - (100. / (1. + rs))
    return rsi

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
    st.success("🤖 المراقبة التلقائية تعمل في الخلفية للسكالبينج والتريند (Futures).")
    
    symbols = ['BTC/USDT', 'ETH/USDT', 'SOL/USDT', 'DOGE/USDT']
    scalp_opps = []
    trend_opps = []
    
    for symbol in symbols:
        try:
            # 1. فحص الاسكالبينج (فريم 5 دقائق)
            ohlcv_5m = exchange.fetch_ohlcv(symbol, '5m', limit=150)
            h5 = np.array([c[2] for c in ohlcv_5m])
            l5 = np.array([c[3] for c in ohlcv_5m])
            c5 = np.array([c[4] for c in ohlcv_5m])
            curr = c5[-1]
            
            ema20_5 = calculate_ema_series(c5, 20)
            ema50_5 = calculate_ema_series(c5, 50)
            macd_5, macds_5 = calculate_macd(c5)
            rsi_5 = calculate_rsi(c5)
            atr_5 = calculate_atr(h5, l5, c5, 14)
            
            long_cross_5 = (ema20_5.iloc[-2] <= ema50_5.iloc[-2]) and (ema20_5.iloc[-1] > ema50_5.iloc[-1])
            short_cross_5 = (ema20_5.iloc[-2] >= ema50_5.iloc[-2]) and (ema20_5.iloc[-1] < ema50_5.iloc[-1])
            
            if long_cross_5 and macd_5 > macds_5 and rsi_5 > 50:
                scalp_opps.append({
                    'symbol': symbol, 'direction': '🟢 LONG (Scalp)', 'price': curr, 'score': 98,
                    'buy': round(curr, 4), 'tp': round(curr + (2.0 * atr_5), 4), 'sl': round(curr - (1.0 * atr_5), 4)
                })
            elif short_cross_5 and macd_5 < macds_5 and rsi_5 < 50:
                scalp_opps.append({
                    'symbol': symbol, 'direction': '🔴 SHORT (Scalp)', 'price': curr, 'score': 98,
                    'buy': round(curr, 4), 'tp': round(curr - (2.0 * atr_5), 4), 'sl': round(curr + (1.0 * atr_5), 4)
                })
                
            # 2. فحص استراتيجية تتبع الاتجاه Trend (فريم 15 دقيقة لتريند أدق)
            ohlcv_15m = exchange.fetch_ohlcv(symbol, '15m', limit=100)
            h15 = np.array([c[2] for c in ohlcv_15m])
            l15 = np.array([c[3] for c in ohlcv_15m])
            c15 = np.array([c[4] for c in ohlcv_15m])
            curr_15 = c15[-1]
            
            ema50_15 = calculate_ema_series(c15, 50)
            ema200_15 = calculate_ema_series(c15, 200)
            atr_15 = calculate_atr(h15, l15, c15, 14)
            
            # تريند صاعد قوي: EMA 50 فوق EMA 200 والسعر فوقهم
            if curr_15 > ema50_15.iloc[-1] and ema50_15.iloc[-1] > ema200_15.iloc[-1]:
                trend_opps.append({
                    'symbol': symbol, 'direction': '📈 LONG (Trend 15m)', 'price': curr_15, 'score': 96,
                    'buy': round(curr_15, 4), 'tp': round(curr_15 + (3.0 * atr_15), 4), 'sl': round(curr_15 - (1.5 * atr_15), 4)
                })
            # تريند هابط قوي: EMA 50 تحت EMA 200 والسعر تحتهم
            elif curr_15 < ema50_15.iloc[-1] and ema50_15.iloc[-1] < ema200_15.iloc[-1]:
                trend_opps.append({
                    'symbol': symbol, 'direction': '📉 SHORT (Trend 15m)', 'price': curr_15, 'score': 96,
                    'buy': round(curr_15, 4), 'tp': round(curr_15 - (3.0 * atr_15), 4), 'sl': round(curr_15 + (1.5 * atr_15), 4)
                })
        except: continue
            
    if (scalp_opps or trend_opps) and (len(scalp_opps) != len(st.session_state.scalping_opps)):
        play_audio_alert()
        
    st.session_state.scalping_opps = scalp_opps
    st.session_state.trend_opps = trend_opps

with col2:
    if st.button('🔄 تحديث المحفظة يدوي'):
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
                                # تعديل دقيق لسرعة إغلاق صفقات الشورت بمجرد ضرب الهدف
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

tab3, tab_trend, tab4 = st.tabs(["⏱️ Scalping (5m)", "🌊 Trend Following (15m)", "💼 محفظتي (دائمة)"])

with tab3:
    st.info("⏱️ إشارات السكالبينج السريعة باستخدام (EMA 20/50 + MACD + RSI).")
    if not st.session_state.scalping_opps:
        st.warning("جاري فحص صفقات السكالبينج اللحظية..")
    else:
        for i, opp in enumerate(st.session_state.scalping_opps, 1):
            st.markdown(f"**{opp['symbol']}** {opp['direction']} | السعر: {opp['price']} | هدف: `{opp['tp']}` | وقف: `{opp['sl']}`")
            if st.button(f"➕ تتبع اسكالبينج", key=f"sc_{i}_{opp['symbol']}"): track_trade(opp, 'Scalping')

with tab_trend:
    st.info("🌊 صفقات تتبع الاتجاه (Trend Following) على فريم 15 دقيقة لركوب الموجات الكبيرة بأمان.")
    if not st.session_state.trend_opps:
        st.warning("جاري البحث عن تريندات قوية واضحة..")
    else:
        for i, opp in enumerate(st.session_state.trend_opps, 1):
            st.markdown(f"**{opp['symbol']}** {opp['direction']} | السعر: {opp['price']} | هدف واسع: `{opp['tp']}` | وقف: `{opp['sl']}`")
            if st.button(f"➕ تتبع تريند", key=f"tr_{i}_{opp['symbol']}"): track_trade(opp, 'Trend')

with tab4:
    if not st.session_state.tracked_trades: st.warning("المحفظة فارغة.")
    else:
        for t in reversed(st.session_state.tracked_trades):
            status_icon = "⚪"
            if "نشطة" in t['status']: status_icon = "🟢"
            elif "ربح" in t['status']: status_icon = "🎯"
            elif "خسارة" in t['status']: status_icon = "🛑"
            st.markdown(f"**{t['symbol']}** | نوع: {t['type']} | {t['direction']} | {status_icon} **{t['status']}**")
            st.markdown(f"دخول: {t['entry']} | هدف: {t['tp']} | وقف: {t['sl']}")
            st.markdown("---")

time.sleep(60)
st.rerun()


