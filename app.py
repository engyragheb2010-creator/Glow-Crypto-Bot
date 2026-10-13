import streamlit as st
import ccxt
import numpy as np
import pandas as pd
import time
import json
import os

st.set_page_config(page_title="Glow Pro Bot", page_icon="📈", layout="wide")
st.title("📈 تطبيق التوصيات الاحترافي (النسخة السحابية الدائمة)")

API_KEY = "41e8e6d1-3d2d-4861-b0df-61ccdb79e34b"
SECRET_KEY = "1FC2FDF62E1F188458144B7700759BC3" 
PASSPHRASE = 'Ahmedengy2010@'

@st.cache_resource
def get_exchange():
    return ccxt.okx({'enableRateLimit': True})

exchange = get_exchange()

# دوال الحفظ الدائم للمحفظة
def load_portfolio():
    if os.path.exists("portfolio.json"):
        try:
            with open("portfolio.json", "r") as f: return json.load(f)
        except: return []
    return []

def save_portfolio(trades):
    with open("portfolio.json", "w") as f: json.dump(trades, f)

if 'spot_opps' not in st.session_state: st.session_state.spot_opps = []
if 'futures_opps' not in st.session_state: st.session_state.futures_opps = []
if 'scalping_opps' not in st.session_state: st.session_state.scalping_opps = []
if 'tracked_trades' not in st.session_state: st.session_state.tracked_trades = load_portfolio()

# --- أدوات التحليل الفني ---
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

def calculate_vwap(highs, lows, closes, volumes):
    typical_price = (highs + lows + closes) / 3
    return np.sum(typical_price * volumes) / np.sum(volumes)

# أدوات السكالبينج الجديدة (ATR, EMA, ADX)
def calculate_ema(prices, period):
    return pd.Series(prices).ewm(span=period, adjust=False).mean().iloc[-1]

def calculate_atr(highs, lows, closes, period=14):
    tr_list = [highs[0] - lows[0]]
    for i in range(1, len(closes)):
        h_l = highs[i] - lows[i]
        h_pc = abs(highs[i] - closes[i-1])
        l_pc = abs(lows[i] - closes[i-1])
        tr_list.append(max(h_l, h_pc, l_pc))
    atr = pd.Series(tr_list).rolling(window=period).mean().iloc[-1]
    return atr if not np.isnan(atr) else (highs[-1] * 0.01)

def calculate_adx(highs, lows, closes, period=14):
    try:
        highs_s = pd.Series(highs)
        lows_s = pd.Series(lows)
        closes_s = pd.Series(closes)
        
        up_move = highs_s - highs_s.shift(1)
        down_move = lows_s.shift(1) - lows_s
        
        plus_dm = np.where((up_move > down_move) & (up_move > 0), up_move, 0)
        minus_dm = np.where((down_move > up_move) & (down_move > 0), down_move, 0)
        
        tr1 = highs_s - lows_s
        tr2 = abs(highs_s - closes_s.shift(1))
        tr3 = abs(lows_s - closes_s.shift(1))
        tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
        
        tr_roll = tr.ewm(alpha=1/period, adjust=False).mean()
        plus_di = 100 * (pd.Series(plus_dm).ewm(alpha=1/period, adjust=False).mean() / tr_roll)
        minus_di = 100 * (pd.Series(minus_dm).ewm(alpha=1/period, adjust=False).mean() / tr_roll)
        
        dx = 100 * abs(plus_di - minus_di) / (plus_di + minus_di)
        adx = dx.ewm(alpha=1/period, adjust=False).mean().iloc[-1]
        return adx if not np.isnan(adx) else 25
    except:
        return 25

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
    if st.button('🔍 فحص السوق بأدوات السكالبينج الديناميكية'):
        with st.spinner('جاري التحليل واستخدام أدوات ATR و الفلاتر الصارمة...'):
            symbols = ['XRP/USDT', 'ETH/USDT', 'SOL/USDT', 'DOGE/USDT', 'ADA/USDT', 'AVAX/USDT', 'LINK/USDT', 'DOT/USDT', 'NEAR/USDT', 'BNB/USDT', 'MATIC/USDT', 'LTC/USDT']
            
            btc_bullish = True
            try:
                btc_ohlcv = exchange.fetch_ohlcv('BTC/USDT', '1h', limit=50)
                if btc_ohlcv[-1][4] < np.mean([c[4] for c in btc_ohlcv[-20:]]): btc_bullish = False
            except: pass
                
            all_1h, all_5m = [], []
            for symbol in symbols:
                try:
                    # فريم الساعة
                    ohlcv_1h = exchange.fetch_ohlcv(symbol, '1h', limit=50)
                    h_1h = np.array([c[2] for c in ohlcv_1h]); l_1h = np.array([c[3] for c in ohlcv_1h]); c_1h = np.array([c[4] for c in ohlcv_1h]); v_1h = np.array([c[5] for c in ohlcv_1h])
                    r_1h = calculate_rsi(c_1h); m_1h, s_1h = calculate_macd(c_1h); vwap_1h = calculate_vwap(h_1h[-20:], l_1h[-20:], c_1h[-20:], v_1h[-20:]); curr = c_1h[-1]
                    
                    sl = 40 + (15 if btc_bullish else 0) + (15 if curr > vwap_1h else 0) + (15 if m_1h > s_1h else 0) + (15 if 40 < r_1h < 70 else 0)
                    ss = 40 + (15 if not btc_bullish else 0) + (15 if curr < vwap_1h else 0) + (15 if m_1h < s_1h else 0) + (15 if 30 < r_1h < 60 else 0)
                    all_1h.append({'symbol': symbol, 'price': curr, 'score_l': sl, 'score_s': ss})
                    
                    # فريم 5 دقائق
                    ohlcv_5m = exchange.fetch_ohlcv(symbol, '5m', limit=50)
                    h_5m = np.array([c[2] for c in ohlcv_5m]); l_5m = np.array([c[3] for c in ohlcv_5m]); c_5m = np.array([c[4] for c in ohlcv_5m]); v_5m = np.array([c[5] for c in ohlcv_5m])
                    curr_5m = c_5m[-1]
                    
                    # حساب المؤشرات الأساسية
                    vwap_5m = calculate_vwap(h_5m[-20:], l_5m[-20:], c_5m[-20:], v_5m[-20:])
                    ema9 = calculate_ema(c_5m, 9)
                    ema21 = calculate_ema(c_5m, 21)
                    atr = calculate_atr(h_5m, l_5m, c_5m, 14)
                    
                    # حساب فلاتر الحماية الثلاثة الجديدة
                    ema20_1h = calculate_ema(c_1h, 20) # 1. الاتجاه العام من فريم الساعة
                    vol_sma20 = np.mean(v_5m[-20:])    # 2. متوسط السيولة لآخر 20 شمعة
                    adx_val = calculate_adx(h_5m, l_5m, c_5m, 14) # 3. قياس الزخم وقوة التريند
                    
                    # التقييم المبدئي
                    sl_5m = 40 + (30 if curr_5m > vwap_5m else 0) + (20 if ema9 > ema21 else 0) + (10 if v_5m[-1] > np.mean(v_5m[-10:]) else 0)
                    ss_5m = 40 + (30 if curr_5m < vwap_5m else 0) + (20 if ema9 < ema21 else 0) + (10 if v_5m[-1] > np.mean(v_5m[-10:]) else 0)
                    
                    # تطبيق الخصم الصارم (Cascade Filtering)
                    if curr_5m < ema20_1h: sl_5m -= 30  # عكس التيار الصاعد
                    if v_5m[-1] < vol_sma20: sl_5m -= 20 # سيولة ضعيفة
                    if adx_val < 25: sl_5m -= 20 # نطاق عرضي متذبذب
                    
                    if curr_5m > ema20_1h: ss_5m -= 30  # عكس التيار الهابط
                    if v_5m[-1] < vol_sma20: ss_5m -= 20 # سيولة ضعيفة
                    if adx_val < 25: ss_5m -= 20 # نطاق عرضي متذبذب
                    
                    # منع التقييم من النزول تحت الصفر
                    sl_5m = max(0, sl_5m)
                    ss_5m = max(0, ss_5m)
                    
                    buy_sl = curr_5m - (1.5 * atr)
                    buy_tp = curr_5m + (2.5 * atr)
                    sell_sl = curr_5m + (1.5 * atr)
                    sell_tp = curr_5m - (2.5 * atr)
                    
                    all_5m.append({
                        'symbol': symbol, 'price': curr_5m, 'score_l': sl_5m, 'score_s': ss_5m,
                        'buy_sl': buy_sl, 'buy_tp': buy_tp, 'sell_sl': sell_sl, 'sell_tp': sell_tp
                    })
                except: continue
                    
            if all_1h and all_5m:
                st.session_state.spot_opps = [{'symbol': i['symbol'], 'price': i['price'], 'score': i['score_l'], 'buy': round(i['price']*0.998,4), 'tp': round(i['price']*1.02,4), 'sl': round(i['price']*0.985,4)} for i in sorted(all_1h, key=lambda x: x['score_l'], reverse=True)[:5]]
                fl = [{'symbol': i['symbol'], 'direction': '🟢 LONG', 'price': i['price'], 'score': i['score_l'], 'buy': round(i['price']*0.998,4), 'tp': round(i['price']*1.025,4), 'sl': round(i['price']*0.98,4), 'leverage': '10x'} for i in sorted(all_1h, key=lambda x: x['score_l'], reverse=True)[:3]]
                fs = [{'symbol': i['symbol'], 'direction': '🔴 SHORT', 'price': i['price'], 'score': i['score_s'], 'buy': round(i['price']*1.002,4), 'tp': round(i['price']*0.975,4), 'sl': round(i['price']*1.02,4), 'leverage': '5x'} for i in sorted(all_1h, key=lambda x: x['score_s'], reverse=True)[:2]]
                st.session_state.futures_opps = sorted(fl + fs, key=lambda x: x['score'], reverse=True)
                
                scl = [{'symbol': i['symbol'], 'direction': '🟢 LONG ATR', 'price': i['price'], 'score': i['score_l'], 'buy': round(i['price'],4), 'tp': round(i['buy_tp'],4), 'sl': round(i['buy_sl'],4), 'leverage': '20x'} for i in sorted(all_5m, key=lambda x: x['score_l'], reverse=True)[:3]]
                scs = [{'symbol': i['symbol'], 'direction': '🔴 SHORT ATR', 'price': i['price'], 'score': i['score_s'], 'buy': round(i['price'],4), 'tp': round(i['sell_tp'],4), 'sl': round(i['sell_sl'],4), 'leverage': '20x'} for i in sorted(all_5m, key=lambda x: x['score_s'], reverse=True)[:2]]
                st.session_state.scalping_opps = sorted(scl + scs, key=lambda x: x['score'], reverse=True)

with col2:
    if st.button('🔄 تحديث المحفظة'):
        with st.spinner('تحديث...'):
            for t in st.session_state.tracked_trades:
                if t['status'] in ['⏳ معلقة', '🟢 نشطة']:
                    try:
                        ticker = exchange.fetch_ticker(t['symbol'])
                        curr = ticker['last']
                        is_long = 'LONG' in t['direction'] or t['type'] == 'Spot'
                        
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
        st.success("تم تنظيف المحفظة! (اضغطي تحديث للرؤية)")
        
    if st.button('🧨 تصفير المحفظة بالكامل'):
        st.session_state.tracked_trades = []
        save_portfolio([])
        st.success("تم مسح كل الصفقات! (اضغطي تحديث للرؤية)")

tab1, tab2, tab3, tab4 = st.tabs(["📊 Spot", "⚡ Futures", "⏱️ Scalping (ATR)", "💼 محفظتي (دائمة)"])

with tab1:
    for i, opp in enumerate(st.session_state.spot_opps, 1):
        st.markdown(f"**{opp['symbol']}** (قوة: {opp['score']}/100 ⭐️) | الحالي: {opp['price']} | دخول: `{opp['buy']}` | هدف: `{opp['tp']}` | وقف: `{opp['sl']}`")
        if st.button(f"➕ تتبع", key=f"s_{i}_{opp['symbol']}"): track_trade(opp, 'Spot')
with tab2:
    for i, opp in enumerate(st.session_state.futures_opps, 1):
        st.markdown(f"**{opp['symbol']}** {opp['direction']} ({opp['score']}/100 ⭐️) | الحالي: {opp['price']} | دخول: `{opp['buy']}` | هدف: `{opp['tp']}` | وقف: `{opp['sl']}`")
        if st.button(f"➕ تتبع", key=f"f_{i}_{opp['symbol']}"): track_trade(opp, 'Futures')
with tab3:
    st.info("💡 يتم فلترة الصفقات بصرامة باستخدام مؤشرات السيولة، اتجاه الساعة، وقوة الزخم (ADX) لمنع الإشارات الوهمية.")
    for i, opp in enumerate(st.session_state.scalping_opps, 1):
        st.markdown(f"**{opp['symbol']}** {opp['direction']} ({opp['score']}/100 ⭐️) | الحالي: {opp['price']} | دخول: `{opp['buy']}` | هدف: `{opp['tp']}` | وقف: `{opp['sl']}`")
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
