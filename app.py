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
st.title("🤖 SMC Sniper Bot - Instant Entry Mode (English Status)")

st_autorefresh(interval=15000, limit=None, key="auto_refresh")

if st.button("🔄 Force Update Price / Refresh Now"):
    st.rerun()

# ==========================================
# 2. إعدادات الذاكرة الدائمة الآمنة (JSON)
# ==========================================
SYMBOLS = ['BTC/USDT', 'ETH/USDT', 'BNB/USDT', 'SOL/USDT', 'LINK/USDT', 'NEAR/USDT', 'SUI/USDT', 'AVAX/USDT', 'ADA/USDT', 'XRP/USDT']
DATA_FILE = 'trades_data.json'

def load_data():
    if os.path.exists(DATA_FILE):
        try:
            with open(DATA_FILE, 'r', encoding='utf-8') as f:
                return json.load(f)
        except:
            return {'active_trades': {}, 'realized_pnl': 0.0}
    return {'active_trades': {}, 'realized_pnl': 0.0}

def save_data():
    data = {
        'active_trades': st.session_state.active_trades,
        'realized_pnl': st.session_state.realized_pnl
    }
    try:
        with open(DATA_FILE, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=4)
    except Exception as e:
        st.error(f"Save error: {e}")

if 'data_loaded' not in st.session_state:
    saved_data = load_data()
    st.session_state.active_trades = saved_data.get('active_trades', {})
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
# 4. دوال التحليل الفني (SMC, ATR & Trend Filter)
# ==========================================
def fetch_data(symbol, timeframe, limit=100):
    try:
        bars = exchange.fetch_ohlcv(symbol, timeframe, limit=limit)
        df = pd.DataFrame(bars, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
        
        df['high'] = pd.to_numeric(df['high'], errors='coerce')
        df['low'] = pd.to_numeric(df['low'], errors='coerce')
        df['close'] = pd.to_numeric(df['close'], errors='coerce')
        
        atr_series = ta.atr(df['high'], df['low'], df['close'], length=14)
        df['ATR'] = atr_series if atr_series is not None and not atr_series.empty else 0.0
        
        ema_series = ta.ema(df['close'], length=50)
        df['EMA50'] = ema_series if ema_series is not None and not ema_series.empty else df['close']
            
        return df
    except Exception as e:
        return None

def analyze_smc(df):
    if df is None or len(df) < 50:
        return 'NONE', 0.0

    last_close = df['close'].iloc[-1]
    prev_high = df['high'].iloc[-2]
    prev_low = df['low'].iloc[-2]
    
    raw_atr = df['ATR'].iloc[-1] if 'ATR' in df.columns else 0.0
    atr_value = float(raw_atr) if (raw_atr is not None and not pd.isna(raw_atr)) else 0.0
    
    ema_val = df['EMA50'].iloc[-1] if 'EMA50' in df.columns else last_close
    
    if last_close > prev_high and last_close > ema_val:
        return 'BUY', atr_value
    elif last_close < prev_low and last_close < ema_val:
        return 'SELL', atr_value
        
    return 'NONE', 0.0

# ==========================================
# عرض إجمالي الأرباح المحققة (Realized PnL)
# ==========================================
st.sidebar.metric(label="💰 Realized Profits (Closed/TP1)", value=f"${st.session_state.realized_pnl:.2f}")

# ==========================================
# 5. محرك التداول وإدارة الأهداف (Instant Entry Modes)
# ==========================================
st.subheader("📊 Live Market Scanner & Portfolio (Instant Entry)")

st.markdown("### 🟢 Active Trades (Persistent)")
if not st.session_state.active_trades:
    st.info("No active trades yet. Scanning for 1h and 15m instant signals...")
    
for sym, trade in list(st.session_state.active_trades.items()):
    try:
        ticker = exchange.fetch_ticker(sym)
        live_price = ticker['last']
        
        side = trade.get('side', 'BUY')
        if side == 'BUY':
            pnl_pct = ((live_price - trade['entry']) / trade['entry']) * 100
        else: 
            pnl_pct = ((trade['entry'] - live_price) / trade['entry']) * 100
            
        pnl_color = "#00ff00" if pnl_pct >= 0 else "#ff4b4b"
        pnl_text = f"<span style='color:{pnl_color}'><b>{pnl_pct:.2f}%</b></span>"
    except:
        live_price = trade['entry']
        pnl_pct = 0.0
        pnl_text = "Loading..."
        side = trade.get('side', 'BUY')

    if 'original_sl' not in trade:
        trade['original_sl'] = trade['sl']

    side_badge = "🟢 BUY" if side == 'BUY' else "🔴 SELL"
    status_msg = ""
    
    if side == 'BUY':
        tp2_reached = live_price >= trade['tp2']
        tp1_reached = live_price >= trade['tp1']
    else: 
        tp2_reached = live_price <= trade['tp2']
        tp1_reached = live_price <= trade['tp1']

    if tp2_reached and pnl_pct > 0:
        if not trade.get('tp2_hit', False):
            tp2_gain_pct = abs((trade['tp2'] - trade['entry']) / trade['entry']) * 100
            st.session_state.realized_pnl += (tp2_gain_pct * 0.5)
            trade['tp2_hit'] = True
            trade['tp1_hit'] = True
            trade['sl'] = trade['entry']
            save_data()
        status_msg = "🚀 **Target 2 Hit (Won)** - Remaining profit added to wallet! Trade remains active until manual removal."
    elif tp1_reached and pnl_pct > 0:
        if not trade.get('tp1_hit', False):
            tp1_gain_pct = abs((trade['tp1'] - trade['entry']) / trade['entry']) * 100
            st.session_state.realized_pnl += (tp1_gain_pct * 0.5) 
            trade['tp1_hit'] = True
            trade['sl'] = trade['entry']  
            save_data()
        status_msg = "🎯 **Target 1 Hit & Profit Secured** - First half profit taken and trade secured at entry. Active until removed."
    else:
        if not trade.get('tp1_hit', False):
            trade['tp1_hit'] = False
            trade['tp2_hit'] = False
            trade['sl'] = trade['original_sl']

    with st.expander(f"{sym} | {side_badge} | {trade['mode']} | PnL: {pnl_pct:.2f}%", expanded=True):
        if status_msg:
            st.success(status_msg)
            
        st.markdown(f"""
        - **Type / Side:** {side_badge}
        - **Mode:** {trade['mode']}
        - **Entry Price:** ${trade['entry']:.4f}
        - **Live Price:** ${live_price:.4f}
        - **Total PnL:** {pnl_text}
        - **🎯 Target 1:** ${trade['tp1']:.4f} {"(✅ Target 1 Hit & Secured)" if trade.get('tp1_hit') and pnl_pct > 0 else ""}
        - **🚀 Target 2:** ${trade['tp2']:.4f} {"(🚀 Target 2 Hit / Won)" if trade.get('tp2_hit') and pnl_pct > 0 else ""}
        - <span style='color:#ff4b4b'>**🛑 Stop Loss:** ${trade['sl']:.4f}</span>
        """, unsafe_allow_html=True)
        
        st.markdown("---")
        if st.button(f"Remove {sym} (Manual)", key=f"remove_active_{sym}"):
            del st.session_state.active_trades[sym]
            save_data()
            st.rerun()

st.markdown("---")

# ==========================================
# 6. رادار السوق ولوب فحص الفرص (دخول فوري للـ Pro والـ Action)
# ==========================================
st.markdown("### 📡 Market Radar (Live Scanner)")
market_radar_data = []

for symbol in SYMBOLS:
    df_1h = fetch_data(symbol, '1h')
    df_15m = fetch_data(symbol, '15m')
    
    if df_15m is None or df_1h is None:
        continue
        
    current_price = df_15m['close'].iloc[-1]
    signal_1h, atr_1h = analyze_smc(df_1h)
    signal_15m, atr_15m = analyze_smc(df_15m)
    volume_15m = df_15m['volume'].iloc[-1]

    raw_atr = df_15m['ATR'].iloc[-1] if 'ATR' in df_15m.columns else 0.0
    atr_val = float(raw_atr) if (raw_atr is not None and not pd.isna(raw_atr)) else 0.0
    atr_display = f"{atr_val:.4f}" if atr_val > 0 else f"{(current_price * 0.01):.4f}"

    if symbol in st.session_state.active_trades:
        status = "🟢 Active Trade"
    else:
        status = "👀 Scanning..."

    market_radar_data.append({
        "🪙 Symbol": symbol,
        "💵 Price": f"${current_price:.4f}",
        "📏 15m ATR": atr_display,
        "📊 Volume": f"{volume_15m:.1f}",
        "Status": status
    })

    if symbol in st.session_state.active_trades:
        continue

    effective_atr_15m = atr_15m if atr_15m > 0 else (current_price * 0.01)

    # 1. فحص إشارات الـ Pro (فريم الساعة) - دخول فوري من السعر الحالي
    if signal_1h in ['BUY', 'SELL'] and symbol not in st.session_state.active_trades:
        try:
            min_target_pct = 0.015
            side = signal_1h
            effective_atr_1h = atr_1h if atr_1h > 0 else (current_price * 0.01)
            
            if side == 'BUY':
                tp1_price = current_price + max(effective_atr_1h * 1.5, current_price * min_target_pct)
                tp2_price = current_price + max(effective_atr_1h * 3.0, current_price * (min_target_pct * 2))
                sl_price = current_price - effective_atr_1h * 1.5
            else: 
                tp1_price = current_price - max(effective_atr_1h * 1.5, current_price * min_target_pct)
                tp2_price = current_price - max(effective_atr_1h * 3.0, current_price * (min_target_pct * 2))
                sl_price = current_price + effective_atr_1h * 1.5

            st.session_state.active_trades[symbol] = {
                'entry': current_price,
                'tp1': tp1_price,
                'tp2': tp2_price,
                'sl': sl_price,
                'original_sl': sl_price,
                'mode': '🎯 Pro (Instant)',
                'side': side,
                'tp1_hit': False,
                'tp2_hit': False
            }
            save_data()
            st.rerun()
        except Exception as e:
            st.error(f"Error placing Pro Instant order: {e}")

    # 2. فحص صفقات الـ Action الفورية (فريم 15 دقيقة)
    elif signal_15m in ['BUY', 'SELL'] and symbol not in st.session_state.active_trades:
        try:
            min_target_pct = 0.015 
            side = signal_15m
            
            if side == 'BUY':
                tp1_price = current_price + max(effective_atr_15m * 1.5, current_price * min_target_pct)
                tp2_price = current_price + max(effective_atr_15m * 3.0, current_price * (min_target_pct * 2))
                sl_price = current_price - effective_atr_15m * 1.5
            else: 
                tp1_price = current_price - max(effective_atr_15m * 1.5, current_price * min_target_pct)
                tp2_price = current_price - max(effective_atr_15m * 3.0, current_price * (min_target_pct * 2))
                sl_price = current_price + effective_atr_15m * 1.5

            st.session_state.active_trades[symbol] = {
                'entry': current_price,
                'tp1': tp1_price,
                'tp2': tp2_price,
                'sl': sl_price,
                'original_sl': sl_price,
                'mode': '🔥 Action',
                'side': side,
                'tp1_hit': False,
                'tp2_hit': False
            }
            save_data()
            st.rerun()
        except Exception as e:
            st.error(f"Error placing Action order: {e}")

st.dataframe(market_radar_data, use_container_width=True)
