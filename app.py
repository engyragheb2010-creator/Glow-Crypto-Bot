import streamlit as st
import ccxt
import numpy as np
import pandas as pd
import time
import json
import os

st.set_page_config(page_title="Glow Pro Master Bot", page_icon="🦅", layout="wide")
st.title("🦅 تطبيق التوصيات الاحترافي (نسخة القناص المتقدم: التريند والدعم والمقاومة)")

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

# مؤشر قوة الاتجاه (ADX) لفلترة التذبذب العرضي
def calculate_adx(highs, lows, closes, period=14):
    plus_dm = np.diff(highs)
    minus_dm = -np.diff(lows)
    plus_dm[plus_dm < 0] = 0
    minus_dm[minus_dm < 0] = 0
    
    tr_list = [highs[0] - lows[0]]
    for i in range(1, len(closes)):
        tr_list.append(max(highs[i] - lows[i], abs(highs[i] - closes[i-1]), abs(lows[i] - closes[i-1])))
    tr = pd.Series(tr_list).rolling(window=period).mean()
    
    plus_di = 100 * (pd.Series(plus_dm).rolling(window=period).mean() / tr)
    minus_di = 100 * (pd.Series(minus_dm).rolling(window=period).mean() / tr)
    dx = 100 * np.abs(plus_di - minus_di) / (plus_di + minus_di)
    adx = dx.rolling(window=period).mean().iloc[-1]
    return adx if not np.isnan(adx) else 20

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
    if st.button('🦅 فحص السوق الاستراتيجي المتقدم'):
        with st.spinner('جاري تحليل الاتجاه (ADX)، الدعم والمقاومة، وباقي المؤشرات...'):
            symbols = ['BTC/USDT', 'ETH/USDT', 'SOL/USDT', 'DOGE/USDT']
            all_opps = []
            
            for symbol in symbols:
                try:
                    ohlcv = exchange.fetch_ohlcv(symbol, '1m', limit=200)
                    h = np.array([c[2] for c in ohlcv])
                    l = np.array([c[3] for c in ohlcv])
                    c = np.array([c[4] for c in ohlcv])
                    v = np.array([c[5] for c in ohlcv])
                    curr = c[-1]
                    
                    # حساب المؤشرات
                    ema5 = calculate_ema_series(c, 5)
                    ema13 = calculate_ema_series(c, 13)
                    macd, macd_signal = calculate_macd(c)
                    rsi = calculate_rsi(c)
                    atr = calculate_atr(h, l, c, 14)
                    adx = calculate_adx(h, l, c, 14)
                    
                    # حساب مستويات الدعم والمقاومة البسيطة (Pivot / High-Low Range)
                    recent_high = np.max(h[-20:])
                    recent_low = np.min(l[-20:])
                    
                    # الشروط الاحترافية
                    long_cross = (ema5.iloc[-2] <= ema13.iloc[-2]) and (ema5.iloc[-1] > ema13.iloc[-1])
                    short_cross = (ema5.iloc[-2] >= ema13.iloc[-2]) and (ema5.iloc[-1] < ema13.iloc[-1])
                    vol_burst = v[-1] > np.mean(v[-6:-1])
                    
                    # فلتر اتجاه السوق: ADX لازم يكون فوق 20 (يعني فيه تريند مش تذبذب رخم)
                    # وفلتر الدعم والمقاومة: Long يكون قريب من الدعم، Short يكون قريب من المقاومة
                    near_support = (curr - recent_low) / (recent_high - recent_low) < 0.4 if recent_high != recent_low else True
                    near_resistance = (recent_high - curr) / (recent_high - recent_low) < 0.4 if recent_high != recent_low else True
                    
                    score = 0
                    direction = ""
                    
                    if long_cross and macd > macd_signal and rsi < 65 and vol_burst and adx > 18 and near_support:
                        score = 100
                        direction = '🟢 LONG قناص'
                        tp = curr + (2.2 * atr)
                        sl = curr - (1.1 * atr)
                    elif short_cross and macd < macd_signal and rsi > 35 and vol_burst and adx > 18 and near_resistance:
                        score = 100
                        direction = '🔴 SHORT قناص'
                        tp = curr - (2.2 * atr)
                        sl = curr + (1.1 * atr)
                    else:
                        continue
                        
                    all_opps.append({
                        'symbol': symbol, 'direction': direction, 'price': curr, 'score': score,
                        'buy': round(curr, 4), 'tp': round(tp, 4), 'sl': round(sl, 4)
                    })
                except: continue
                    
            st.session_state.scalping_opps = all_opps

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
                                elif >= t['sl']: t['status'] = '🛑 خسارة (Hit SL)'
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

tab3, tab4 = st.tabs(["⏱️ Scalping (استراتيجية القناص المتكاملة)", "💼 محفظتي (دائمة)"])

with tab3:
    st.info("🦅 البوت يدمج الآن فلتر قوة التريند (ADX) ومناطق الدعم والمقاومة مع مؤشرات الزخم والسيولة لضمان أعلى دقة ممكنة.")
    if not st.session_state.scalping_opps:
        st.warning("البوت يراقب السوق بدقة.. في انتظار توافق التريند ومناطق الدعم/المقاومة الحقيقية.")
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


