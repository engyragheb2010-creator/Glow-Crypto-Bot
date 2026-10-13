import streamlit as st
import ccxt
import numpy as np
import pandas as pd
import time
import json
import os

st.set_page_config(page_title="Glow Pro Bot", page_icon="📈", layout="wide")
st.title("📈 تطبيق التوصيات الاحترافي (نسخة الشموع المغلقة المؤكدة)")

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

if 'spot_opps' not in st.session_state: st.session_state.spot_opps = []
if 'futures_opps' not in st.session_state: st.session_state.futures_opps = []
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
    if st.button('🔍 فحص السوق بأدوات السكالبينج السريعة'):
        with st.spinner('جاري قنص الصفقات (الشموع المغلقة فقط)...'):
            symbols = ['XRP/USDT', 'ETH/USDT', 'SOL/USDT', 'DOGE/USDT', 'ADA/USDT', 'AVAX/USDT', 'LINK/USDT', 'DOT/USDT', 'NEAR/USDT', 'BNB/USDT', 'MATIC/USDT', 'LTC/USDT']
            
            btc_bullish = True
            try:
                btc_ohlcv = exchange.fetch_ohlcv('BTC/USDT', '1h', limit=500)
                if btc_ohlcv[-2][4] < np.mean([c[4] for c in btc_ohlcv[-21:-1]]): btc_bullish = False
            except: pass
                
            all_1h, all_5m = [], []
            for symbol in symbols:
                try:
                    # فريم الساعة
                    ohlcv_1h = exchange.fetch_ohlcv(symbol, '1h', limit=500)
                    h_1h = np.array([c[2] for c in ohlcv_1h]); l_1h = np.array([c[3] for c in ohlcv_1h]); c_1h = np.array([c[4] for c in ohlcv_1h]); v_1h = np.array([c[5] for c in ohlcv_1h])
                    r_1h = calculate_rsi(c_1h[:-1]); m_1h, s_1h = calculate_macd(c_1h[:-1]); vwap_1h = calculate_vwap(h_1h[-21:-1], l_1h[-21:-1], c_1h[-21:-1], v_1h[-21:-1]); curr_1h_closed = c_1h[-2]
                    ema20_1h = calculate_ema_series(c_1h, 20).iloc[-2]
                    
                    sl = 40 + (15 if btc_bullish else 0) + (15 if curr_1h_closed > vwap_1h else 0) + (15 if m_1h > s_1h else 0) + (15 if 40 < r_1h < 70 else 0)
                    ss = 40 + (15 if not btc_bullish else 0) + (15 if curr_1h_closed < vwap_1h else 0) + (15 if m_1h < s_1h else 0) + (15 if 30 < r_1h < 60 else 0)
                    all_1h.append({'symbol': symbol, 'price': curr_1h_closed, 'score_l': sl, 'score_s': ss})
                    
                    # فريم 5 دقائق لحساب الأهداف
                    ohlcv_5m = exchange.fetch_ohlcv(symbol, '5m', limit=500)
                    h_5m = np.array([c[2] for c in ohlcv_5m]); l_5m = np.array([c[3] for c in ohlcv_5m]); c_5m = np.array([c[4] for c in ohlcv_5m])
                    curr_5m = c_5m[-1] # سعر الدخول الحالي
                    atr = calculate_atr(h_5m[:-1], l_5m[:-1], c_5m[:-1], 14)
                    
                    # فريم الدقيقة 1m (هنا التعديل الجوهري: استخدام الشموع المغلقة فقط)
                    ohlcv_1m = exchange.fetch_ohlcv(symbol, '1m', limit=500)
                    c_1m = np.array([c[4] for c in ohlcv_1m])
                    v_1m = np.array([c[5] for c in ohlcv_1m])
                    
                    ema5_series = calculate_ema_series(c_1m, 5)
                    ema13_series = calculate_ema_series(c_1m, 13)
                    
                    # (-2) هي آخر شمعة قفلت فعلاً، و (-3) هي اللي قبلها
                    ema5_closed = ema5_series.iloc[-2]
                    ema13_closed = ema13_series.iloc[-2]
                    ema5_prev_closed = ema5_series.iloc[-3]
                    ema13_prev_closed = ema13_series.iloc[-3]
                    
                    # التأكد من التقاطع المؤكد على الشموع المغلقة
                    confirmed_long = (ema5_prev_closed <= ema13_prev_closed) and (ema5_closed > ema13_closed)
                    confirmed_short = (ema5_prev_closed >= ema13_prev_closed) and (ema5_closed < ema13_closed)
                    
                    # سيولة الشمعة المغلقة
                    vol_burst = v_1m[-2] > np.mean(v_1m[-7:-2])

                    sl_5m = 50 + (30 if confirmed_long else 0) + (20 if vol_burst else 0)
                    ss_5m = 50 + (30 if confirmed_short else 0) + (20 if vol_burst else 0)
                    
                    if c_1m[-2] < ema20_1h: sl_5m -= 50
                    if c_1m[-2] > ema20_1h: ss_5m -= 50
                    
                    if not confirmed_long: sl_5m -= 50
                    if not confirmed_short: ss_5m -= 50
                    
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
                scl = [{'symbol': i['symbol'], 'direction': '🟢 LONG مؤكد', 'price': i['price'], 'score': i['score_l'], 'buy': round(i['price'],4), 'tp': round(i['buy_tp'],4), 'sl': round(i['buy_sl'],4), 'leverage': '20x'} for i in sorted(all_5m, key=lambda x: x['score_l'], reverse=True)[:3]]
                scs = [{'symbol': i['symbol'], 'direction': '🔴 SHORT مؤكد', 'price': i['price'], 'score': i['score_s'], 'buy': round(i['price'],4), 'tp': round(i['sell_tp'],4), 'sl': round(i['sell_sl'],4), 'leverage': '20x'} for i in sorted(all_5m, key=lambda x: x['score_s'], reverse=True)[:2]]
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

tab3, tab4 = st.tabs(["⏱️ Scalping (مؤكد)", "💼 محفظتي (دائمة)"])

with tab3:
    st.info("⚡ البوت الآن يتجاهل الشمعة الحالية تماماً ولا يقرأ إلا التقاطعات التي اكتملت وأغلقت على الشارت لضمان عدم وجود إشارات وهمية.")
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
