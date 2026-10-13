import streamlit as st
import ccxt
import numpy as np
import pandas as pd
import time
import json
import os

st.set_page_config(page_title="Glow Pro Bot", page_icon="📈", layout="wide")
st.title("📈 تطبيق التوصيات الاحترافي (نسخة العرض الفوري السريع)")

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

def calculate_rsi(prices, period=14):
    deltas = np.diff(prices)
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
            rs = 100. - (100. / (1. + rs))
    return rsi

def calculate_macd(prices):
    exp1 = pd.Series(prices).ewm(span=12, adjust=False).mean()
    exp2 = pd.Series(prices).ewm(span=26, adjust=False).mean()
    macd = exp1 - exp2
    signal = macd.ewm(span=9, adjust=False).mean()
    return macd.iloc[-1], signal.iloc[-1]

def calculate_vwap(highs, lows, closes, volumes):
    typical_price = (highs + lows + closes) / 3
    return np.sum(typical_price * volumes) / np.sum(volumes)

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
    if st.button('🔍 فحص السوق السريع'):
        with st.spinner('جاري الفحص...'):
            symbols = ['SOL/USDT', 'DOGE/USDT', 'BTC/USDT', 'ETH/USDT', 'XRP/USDT', 'LTC/USDT']
            
            all_opps = []
            for symbol in symbols:
                try:
                    # سحب 200 شمعة فريم الدقيقة للسرعة والدقة
                    ohlcv_1m = exchange.fetch_ohlcv(symbol, '1m', limit=200)
                    h_1m = np.array([c[2] for c in ohlcv_1m])
                    l_1m = np.array([c[3] for c in ohlcv_1m])
                    c_1m = np.array([c[4] for c in ohlcv_1m])
                    v_1m = np.array([c[5] for c in ohlcv_1m])
                    curr = c_1m[-1]
                    
                    ema5 = calculate_ema_series(c_1m, 5)
                    ema13 = calculate_ema_series(c_1m, 13)
                    atr = calculate_atr(h_1m, l_1m, c_1m, 14)
                    
                    # فحص التقاطع الحالي
                    is_long = ema5.iloc[-1] > ema13.iloc[-1]
                    fresh_cross = (ema5.iloc[-2] <= ema13.iloc[-2]) and is_long if is_long else (ema5.iloc[-2] >= ema13.iloc[-2]) and not is_long
                    
                    score = 50
                    if fresh_cross: score += 30
                    if v_1m[-1] > np.mean(v_1m[-6:-1]): score += 20
                    
                    direction = '🟢 LONG سريع' if is_long else '🔴 SHORT سريع'
                    buy_price = curr
                    tp = curr + (2.0 * atr) if is_long else curr - (2.0 * atr)
                    sl = curr - (1.0 * atr) if is_long else curr + (1.0 * atr)
                    
                    all_opps.append({
                        'symbol': symbol, 'direction': direction, 'price': curr, 'score': score,
                        'buy': round(buy_price, 4), 'tp': round(tp, 4), 'sl': round(sl, 4)
                    })
                except: continue
                    
            if all_opps:
                st.session_state.scalping_opps = sorted(all_opps, key=lambda x: x['score'], reverse=True)

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

tab3, tab4 = st.tabs(["⏱️ Scalping (الفحص المباشر)", "💼 محفظتي (دائمة)"])

with tab3:
    st.info("⚡ البوت يعرض الآن حالة السوق والعملات فوراً مع تقييماتها المباشرة لتجنب الشاشات الفارغة.")
    if not st.session_state.scalping_opps:
        st.warning("اضغط على زر (فحص السوق السريع) أعلاه لجلب البيانات فوراً.")
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
