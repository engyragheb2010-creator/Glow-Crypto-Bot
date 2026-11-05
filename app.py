import streamlit as st
from streamlit_autorefresh import st_autorefresh
import ccxt
import pandas as pd
import pandas_ta as ta
import time
import json
import os

# ==========================================
# 1. إعدادات الشاشة الأساسية والتحديث التلقائي (كل 15 ثانية)
# ==========================================
st.set_page_config(page_title="SMC Sniper Bot", layout="wide")
st.title("🤖 SMC Sniper Bot - Paper Trading Simulator")

st_autorefresh(interval=15000, limit=None, key="auto_refresh")

# زرار التحديث اليدوي الفوري (Force Update)
if st.button("🔄 Force Update Price / Refresh Now"):
    st.rerun()

# ==========================================
# 2. إعدادات البوت والذاكرة الدائمة (JSON)
# ==========================================
MAX_OPEN_TRADES = 99  
SYMBOLS = ['BTC/USDT', 'ETH/USDT', 'BNB/USDT', 'SOL/USDT', 'LINK/USDT', 'NEAR/USDT', 'SUI/USDT', 'AVAX/USDT', 'ADA/USDT', 'XRP/USDT']

DATA_FILE = 'trades_data.json'

def load_data():
    if os.path.exists(DATA_FILE):
        try:
            with open(DATA_FILE, 'r') as f:
                return json.load(f)
        except:
            return {'active_trades': {}, 'pending_orders': {}, 'resting_symbols': {}, 'realized_pnl': 0.0}
    return {'active_trades': {}, 'pending_orders': {}, 'resting_symbols': {}, 'realized_pnl': 0.0}

def save_data():
    data = {
        'active_trades': st.session_state.active_trades,
        'pending_orders': st.session_state.pending_orders,
        'resting_symbols': st.session_state.resting_symbols,
        'realized_pnl': st.session_state.realized_pnl
    }
    with open(DATA_FILE, 'w') as f:
        json.dump(data, f)

if 'data_loaded' not in st.session_state:
    saved_data = load_data()
    st.session_state.active_trades = saved_data.get('active_trades', {})
    st.session_state.pending_orders = saved_data.get('pending_orders', {})
    st.session_state.resting_symbols = saved_data.get('resting_symbols', {})
    st.session_state.realized_pnl = saved_data.get('realized_pnl', 0.0)
    st.session_state.data_loaded = True

# ==========================================
# 3. الاتصال بمنصة OKX (للقراءة فقط)
# ==========================================
try:
    exchange = ccxt.okx({
        'enableRateLimit': True,
    })
except Exception as e:
    st.error(f"Error connecting to OKX: {e}")

# ==========================================
# 4. دوال التحليل الفني (SMC & ATR الآمنة)
# ==========================================
def fetch_data(symbol, timeframe, limit=100):
    try:
        bars = exchange.fetch_ohlcv(symbol, timeframe, limit=limit)
        df = pd.DataFrame(bars, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
        
        df['high'] = pd.to_numeric(df['high'], errors='coerce')
        df['low'] = pd.to_numeric(df['low'], errors='coerce')
        df['close'] = pd.to_numeric(df['close'], errors='coerce')
        
        atr_series = ta.atr(df['high'], df['low'], df['close'], length=14)
        if atr_series is not None and not atr_series.empty:
            df['ATR'] = atr_series
        else:
            df['ATR'] = 0.0
            
        return df
    except Exception as e:
        return None

def analyze_smc(df):
    if df is None or len(df) < 3:
        return 'NONE', 0.0, 0.0

    last_close = df['close'].iloc[-1]
    prev_high = df['high'].iloc[-2]
    
    raw_atr = df['ATR'].iloc[-1] if 'ATR' in df.columns else 0.0
    atr_value = float(raw_atr) if (raw_atr is not None and not pd.isna(raw_atr)) else 0.0
    
    is_breakout = last_close > prev_high 
    fvg_price = df['low'].iloc[-1] + (df['high'].iloc[-1] - df['low'].iloc[-1]) * 0.5
    
    if is_breakout:
        return 'BUY', fvg_price, atr_value
    return 'NONE', 0.0, 0.0

# ==========================================
# عرض إجمالي الأرباح المحققة (Realized PnL)
# ==========================================
st.sidebar.metric(label="💰 Realized Profits (Closed/TP1)", value=f"${st.session_state.realized_pnl:.2f}")

# ==========================================
# 5. محرك التداول وإدارة الأهداف وجني الأرباح الجزئي
# ==========================================
st.subheader("📊 Live Market Scanner & Portfolio")
col1, col2 = st.columns(2)

with col1:
    st.markdown("### 🟢 Active Trades")
    if not st.session_state.active_trades:
        st.info("No active trades yet. Waiting for breakouts or pending triggers...")
        
    for sym, trade in list(st.session_state.active_trades.items()):
        try:
            ticker = exchange.fetch_ticker(sym)
            live_price = ticker['last']
            
            pnl_pct = ((live_price - trade['entry']) / trade['entry']) * 100
            pnl_color = "#00ff00" if pnl_pct >= 0 else "#ff4b4b"
            pnl_text = f"<span style='color:{pnl_color}'><b>{pnl_pct:.2f}%</b></span>"
        except:
            live_price = trade['entry']
            pnl_pct = 0.0
            pnl_text = "Loading..."

        if 'original_sl' not in trade:
            trade['original_sl'] = trade['sl']

        status_msg = ""
        
        if live_price >= trade['tp2'] and pnl_pct > 0:
            trade['tp2_hit'] = True
            trade['tp1_hit'] = True
            trade['sl'] = trade['entry']
            save_data()
            status_msg = "🚀 **مبروك! تم ضرب الهدف الثاني (Target 2) وإغلاق الصفقة بالكامل بربح كلي!**"
        elif live_price >= trade['tp1'] and pnl_pct > 0:
            if not trade.get('tp1_hit', False):
                tp1_gain_pct = ((trade['tp1'] - trade['entry']) / trade['entry']) * 100
                st.session_state.realized_pnl += (tp1_gain_pct * 0.5) 
                trade['tp1_hit'] = True
                trade['sl'] = trade['entry']  
                save_data()
            status_msg = "🎯 **رائع! تم ضرب الهدف الأول (Target 1)، وتم أخذ جزء من الأرباح وتأمين الباقي عند نقطة الدخول (Break-even).**"
        else:
            if not trade.get('tp1_hit', False):
                trade['tp1_hit'] = False
                trade['tp2_hit'] = False
                trade['sl'] = trade['original_sl']

        with st.expander(f"{sym} | {trade['mode']} | PnL: {pnl_pct:.2f}%", expanded=True):
            if status_msg:
                st.success(status_msg)
                
            st.markdown(f"""
            - **Mode:** {trade['mode']}
            - **Entry Price:** ${trade['entry']:.4f}
            - **Live Price:** ${live_price:.4f}
            - **Total PnL:** {pnl_text}
            - **🎯 Target 1:** ${trade['tp1']:.4f} {"(✅ TP1 Hit & Secured)" if trade.get('tp1_hit') and pnl_pct > 0 else ""}
            - **🚀 Target 2:** ${trade['tp2']:.4f} {"(🚀 Hit)" if trade.get('tp2_hit') and pnl_pct > 0 else ""}
            - <span style='color:#ff4b4b'>**🛑 Stop Loss:** ${trade['sl']:.4f}</span>
            """, unsafe_allow_html=True)
            
            st.markdown("---")
            if st.button(f"Remove {sym}", key=f"remove_active_{sym}"):
                del st.session_state.active_trades[sym]
                save_data()  
                st.rerun()

with col2:
    st.markdown("### ⏳ Pending Orders (Pro Sniping)")
    if not st.session_state.pending_orders:
        st.info("No pending orders. Scanning 1h timeframe...")
        
    for sym, order in list(st.session_state.pending_orders.items()):
        with st.expander(f"{sym} | {order['mode']} | Waiting at Fvg: ${order['fvg_price']:.4f}", expanded=True):
            st.markdown(f"""
            - **Mode:** {order['mode']}
            - **Net Waiting Price:** ${order['fvg_price']:.4f}
            """, unsafe_allow_html=True)
            
            st.markdown("---")
            if st.button(f"Cancel {sym}", key=f"cancel_pending_{sym}"):
                del st.session_state.pending_orders[sym]
                save_data() 
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

    raw_atr = df_15m['ATR'].iloc[-1] if 'ATR' in df_15m.columns else 0.0
    atr_val = float(raw_atr) if (raw_atr is not None and not pd.isna(raw_atr)) else 0.0
    atr_display = f"{atr_val:.4f}" if atr_val > 0 else f"{(current_price * 0.01):.4f}"

    if symbol in st.session_state.pending_orders:
        pending_order = st.session_state.pending_orders[symbol]
        fvg_entry = pending_order['fvg_price']
        
        if current_low <= fvg_entry:
            saved_atr = pending_order['atr'] if pending_order['atr'] > 0 else (current_price * 0.01)
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
                'original_sl': sl_price,
                'mode': '🎯 Pro (Triggered)',
                'tp1_hit': False,
                'tp2_hit': False
            }
            del st.session_state.pending_orders[symbol]
            save_data() 
            st.rerun()

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
        "📏 15m ATR": atr_display,
        "📊 Volume": f"{volume_15m:.1f}",
        "Status": status
    })

    if symbol in st.session_state.active_trades or symbol in st.session_state.pending_orders:
        continue
        
    if symbol in st.session_state.resting_symbols:
        if time.time() - st.session_state.resting_symbols[symbol] > 900: 
            del st.session_state.resting_symbols[symbol]
            save_data()
        continue

    effective_atr_15m = atr_15m if atr_15m > 0 else (current_price * 0.01)
    effective_atr_1h = atr_1h if atr_1h > 0 else (current_price * 0.01)

    if signal_1h == 'BUY':
        try:
            st.session_state.pending_orders[symbol] = {
                'fvg_price': fvg_price_1h,
                'atr': effective_atr_1h,
                'mode': '🎯 Pro'
            }
            save_data() 
            st.rerun()
        except Exception as e:
            st.error(f"Error placing Pro order for {symbol}: {e}")

    elif signal_15m == 'BUY':
        try:
            min_target_pct = 0.015 
            tp1_dist = effective_atr_15m * 1.5
            tp2_dist = effective_atr_15m * 3.0
            sl_dist = effective_atr_15m * 1.5
            
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
                'original_sl': sl_price,
                'mode': '🔥 Action',
                'tp1_hit': False,
                'tp2_hit': False
            }
            save_data() 
            st.rerun()
        except Exception as e:
            st.error(f"Error placing Action order for {symbol}: {e}")

st.dataframe(market_radar_data, use_container_width=True)
