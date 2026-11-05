import streamlit as st
from streamlit_autorefresh import st_autorefresh
import ccxt
import pandas as pd
import pandas_ta as ta
import time
import json
import os

# ==========================================
# 1. إعدادات الشاشة الأساسية والتحديث التلقائي
# ==========================================
st.set_page_config(page_title="SMC Sniper Bot", layout="wide")
st.title("🤖 SMC Sniper Bot - Paper Trading Simulator")

# تحديث الشاشة كل دقيقة (60,000 ملي ثانية) 
st_autorefresh(interval=60000, limit=None, key="auto_refresh")

# ==========================================
# 2. إعدادات البوت وإدارة المخاطر والذاكرة الدائمة
# ==========================================
MAX_OPEN_TRADES = 99  
SYMBOLS = ['BTC/USDT', 'ETH/USDT', 'BNB/USDT', 'SOL/USDT', 'LINK/USDT', 'NEAR/USDT', 'SUI/USDT', 'AVAX/USDT', 'ADA/USDT', 'XRP/USDT']

DATA_FILE = 'trades_data.json'

# دالة لقراءة البيانات من الملف 
def load_data():
    if os.path.exists(DATA_FILE):
        try:
            with open(DATA_FILE, 'r') as f:
                return json.load(f)
        except:
            return {'active_trades': {}, 'pending_orders': {}, 'resting_symbols': {}}
    return {'active_trades': {}, 'pending_orders': {}, 'resting_symbols': {}}

# دالة لحفظ البيانات في الملف
def save_data():
    data = {
        'active_trades': st.session_state.active_trades,
        'pending_orders': st.session_state.pending_orders,
        'resting_symbols': st.session_state.resting_symbols
    }
    with open(DATA_FILE, 'w') as f:
        json.dump(data, f)

# تحميل البيانات أول مرة الشاشة تفتح
if 'data_loaded' not in st.session_state:
    saved_data = load_data()
    st.session_state.active_trades = saved_data.get('active_trades', {})
    st.session_state.pending_orders = saved_data.get('pending_orders', {})
    st.session_state.resting_symbols = saved_data.get('resting_symbols', {})
    st.session_state.data_loaded = True

# ==========================================
# 3. الاتصال بمنصة OKX (للقراءة فقط - بدون مفاتيح)
# ==========================================
try:
    # اتصال عام لجلب الأسعار الحية فقط بدون أي API Keys
    exchange = ccxt.okx({
        'enableRateLimit': True,
    })
except Exception as e:
    st.error(f"Error connecting to OKX: {e}")

# ==========================================
# 4. دوال التحليل الفني (SMC & ATR)
# ==========================================
def fetch_data(symbol, timeframe, limit=100):
    try:
        bars = exchange.fetch_ohlcv(symbol, timeframe, limit=limit)
        df = pd.DataFrame(bars, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
        df['ATR'] = ta.atr(df['high'], df['low'], df['close'], length=14)
        return df
    except Exception as e:
        return None

def analyze_smc(df):
    if df is None or len(df) < 3:
        return 'NONE', 0.0, 0.0

    last_close = df['close'].iloc[-1]
    prev_high = df['high'].iloc[-2]
    atr_value = df['ATR'].iloc[-1]
    
    is_breakout = last_close > prev_high 
    # حساب منطقة FVG (كمثال: منتصف الشمعة)
    fvg_price = df['low'].iloc[-1] + (df['high'].iloc[-1] - df['low'].iloc[-1]) * 0.5
    
    if is_breakout:
        return 'BUY', fvg_price, atr_value
    return 'NONE', 0.0, 0.0

# ==========================================
# 5. محرك التداول وعرض الشاشة (الـ Portfolio)
# ==========================================
st.subheader("📊 Live Market Scanner & Portfolio")
col1, col2 = st.columns(2)

with col1:
    st.markdown("### 🟢 Active Trades")
    if not st.session_state.active_trades:
        st.info("No active trades yet. Waiting for breakouts or pending triggers...")
        
    for sym, trade in list(st.session_state.active_trades.items()):
        with st.expander(f"{sym} | {trade['mode']} | Entry: ${trade['entry']:.4f}", expanded=True):
            st.markdown(f"""
            - **Mode:** {trade['mode']}
            - **Entry Price:** ${trade['entry']:.4f}
            - **🎯 Target 1:** ${trade['tp1']:.4f}
            - **🚀 Target 2:** ${trade['tp2']:.4f}
            - <span style='color:#ff4b4b'>**🛑 Stop Loss:** ${trade['sl']:.4f}</span>
            """, unsafe_allow_html=True)
            
            st.markdown("---")
            if st.button(f"Remove {sym}", key=f"remove_active_{sym}"):
                del st.session_state.active_trades[sym]
                save_data()  # حفظ بعد الحذف
                st.rerun()

with col2:
    st.markdown("### ⏳ Pending Orders (Pro Sniping)")
    if not st.session_state.pending_orders:
        st.info("No pending orders. Scanning 1h timeframe...")
        
    for sym, order in list(st.session_state.pending_orders.items()):
        with st.expander(f"{sym} | {order['mode']} | Waiting at FVG: ${order['fvg_price']:.4f}", expanded=True):
            st.markdown(f"""
            - **Mode:** {order['mode']}
            - **Net Waiting Price:** ${order['fvg_price']:.4f}
            """, unsafe_allow_html=True)
            
            st.markdown("---")
            if st.button(f"Cancel {sym}", key=f"cancel_pending_{sym}"):
                del st.session_state.pending_orders[sym]
                save_data() # حفظ بعد الحذف
                st.rerun()

st.markdown("---")

# ==========================================
# 6. رادار السوق ولوب فحص الفرص
# ==========================================
st.markdown("### 📡 Market Radar (Live Scanner)")
market_radar_data = []

for symbol in SYMBOLS:
    df_1h = fetch_data(symbol, '1h')
    df_15m = fetch_data(symbol, '15m')
    
    if df_15m is None or df_1h is None:
        continue
        
    current_price = df_15m['close'].iloc[-1]
    current_low = df_15m['low'].iloc[-1]  
    
    signal_1h, fvg_price_1h, atr_1h = analyze_smc(df_1h)
    signal_15m, _, atr_15m = analyze_smc(df_15m)
    volume_15m = df_15m['volume'].iloc[-1]

    # --- مراقبة وتفعيل الأوامر المعلقة (Pro Trigger) ---
    if symbol in st.session_state.pending_orders:
        pending_order = st.session_state.pending_orders[symbol]
        fvg_entry = pending_order['fvg_price']
        
        # لو السعر نزل ضرب نقطة الدخول المعلقة
        if current_low <= fvg_entry:
            saved_atr = pending_order['atr']
            min_target_pct = 0.015
            
            tp1_dist = saved_atr * 1.5
            tp2_dist = saved_atr * 3.0
            sl_dist = saved_atr * 1.5
            
            if (tp1_dist / fvg_entry) < min_target_pct:
                tp1_price = fvg_entry * (1 + min_target_pct)
                tp2_price = fvg_entry * (1 + (min_target_pct * 2.0))
                sl_price = fvg_entry * (1 - min_target_pct)
            else:
                tp1_price = fvg_entry + tp1_dist
                tp2_price = fvg_entry + tp2_dist
                sl_price = fvg_entry - sl_dist

            st.session_state.active_trades[symbol] = {
                'entry': fvg_entry,
                'tp1': tp1_price,
                'tp2': tp2_price,
                'sl': sl_price,
                'mode': '🎯 Pro (Triggered)'
            }
            del st.session_state.pending_orders[symbol]
            save_data() # حفظ التغيير
            st.rerun()

    # --- تحديد حالة العملة لجدول الرادار ---
    if symbol in st.session_state.active_trades:
        status = "🟢 Active Trade"
    elif symbol in st.session_state.pending_orders:
        status = "⏳ Pending (Pro)"
    elif symbol in st.session_state.resting_symbols:
        status = "💤 Resting"
    else:
        status = "👀 Scanning..."

    market_radar_data.append({
        "🪙 Symbol": symbol,
        "💵 Price": f"${current_price:.4f}",
        "📏 15m ATR": f"{atr_15m:.4f}",
        "📊 Volume": f"{volume_15m:.1f}",
        "Status": status
    })

    # --- منطق اصطياد فرص جديدة ---
    if symbol in st.session_state.active_trades or symbol in st.session_state.pending_orders:
        continue
        
    if symbol in st.session_state.resting_symbols:
        if time.time() - st.session_state.resting_symbols[symbol] > 900: 
            del st.session_state.resting_symbols[symbol]
            save_data()
        continue

    # قرار القناص (Pro)
    if signal_1h == 'BUY':
        try:
            st.session_state.pending_orders[symbol] = {
                'fvg_price': fvg_price_1h,
                'atr': atr_1h,
                'mode': '🎯 Pro'
            }
            save_data() # حفظ الأمر الجديد
            st.rerun()
        except Exception as e:
            st.error(f"Error placing Pro order for {symbol}: {e}")

    # قرار الانفجار (Action)
    elif signal_15m == 'BUY':
        try:
            min_target_pct = 0.015 
            tp1_dist = atr_15m * 1.5
            tp2_dist = atr_15m * 3.0
            sl_dist = atr_15m * 1.5
            
            if (tp1_dist / current_price) < min_target_pct:
                tp1_price = current_price * (1 + min_target_pct)
                tp2_price = current_price * (1 + (min_target_pct * 2.0))
                sl_price = current_price * (1 - min_target_pct)
            else:
                tp1_price = current_price + tp1_dist
                tp2_price = current_price + tp2_dist
                sl_price = current_price - sl_dist

            st.session_state.active_trades[symbol] = {
                'entry': current_price,
                'tp1': tp1_price,
                'tp2': tp2_price,
                'sl': sl_price,
                'mode': '🔥 Action'
            }
            save_data() # حفظ الصفقة الجديدة
            st.rerun()
        except Exception as e:
            st.error(f"Error placing Action order for {symbol}: {e}")

# عرض جدول الرادار تحت الصفقات
st.dataframe(market_radar_data, use_container_width=True)
