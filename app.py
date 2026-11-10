import streamlit as st
from streamlit_autorefresh import st_autorefresh
import ccxt
import pandas as pd
import pandas_ta as ta
import time
import json
import os
from datetime import datetime

# ==========================================
# 1. إعدادات الشاشة الأساسية والتحديث التلقائي
# ==========================================
st.set_page_config(page_title="SMC Sniper Bot", layout="wide")
st.title("🤖 SMC Sniper Bot - Smart Resting on Manual Remove")

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
                data = json.load(f)
                if 'realized_pnl' not in data:
                    data['realized_pnl'] = 18.75
                return data
        except:
            return {'active_trades': {}, 'closed_trades': [], 'cooldowns': {}, 'realized_pnl': 18.75}
    return {'active_trades': {}, 'closed_trades': [], 'cooldowns': {}, 'realized_pnl': 18.75}

def save_data():
    data = {
        'active_trades': st.session_state.active_trades,
        'closed_trades': st.session_state.closed_trades,
        'cooldowns': st.session_state.cooldowns,
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
    st.session_state.closed_trades = saved_data.get('closed_trades', [])
    st.session_state.cooldowns = saved_data.get('cooldowns', {})
    
    loaded_pnl = saved_data.get('realized_pnl', 18.75)
    st.session_state.realized_pnl = loaded_pnl if loaded_pnl != 0.0 else 18.75
    
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
# 4. دوال التحليل الفني وحساب المدة
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

def format_duration(seconds):
    mins = int(seconds // 60)
    hours = mins // 60
    mins = mins % 60
    days = hours // 24
    hours = hours % 24
    if days > 0:
        return f"{days}d {hours}h {mins}m"
    elif hours > 0:
        return f"{hours}h {mins}m"
    else:
        return f"{mins} mins"

# ==========================================
# عرض إجمالي الأرباح والخسائر المحققة (Realized PnL)
# ==========================================
pnl_color_sidebar = "#00ff00" if st.session_state.realized_pnl >= 0 else "#ff4b4b"
st.sidebar.markdown(f"### 💰 Realized PnL")
st.sidebar.markdown(f"<h2 style='color:{pnl_color_sidebar}; margin-top:-15px;'>${st.session_state.realized_pnl:.2f}</h2>", unsafe_allow_html=True)

# ==========================================
# 5. صفقات التداول النشطة والمغلقة
# ==========================================
st.subheader("📊 Live Market Scanner & Active Portfolio")

st.markdown("### 🟢 Active Trades (Persistent)")
if not st.session_state.active_trades:
    st.info("No active trades yet. Scanning for instant signals...")
    
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

    open_ts = trade.get('open_timestamp', time.time())
    current_duration = format_duration(time.time() - open_ts) if trade.get('open_timestamp') else "N/A"

    side_badge = "🟢 BUY" if side == 'BUY' else "🔴 SELL"
    
    if side == 'BUY':
        tp2_reached = live_price >= trade['tp2']
        tp1_reached = live_price >= trade['tp1']
        sl_hit = live_price <= trade['sl']
    else: 
        tp2_reached = live_price <= trade['tp2']
        tp1_reached = live_price <= trade['tp1']
        sl_hit = live_price >= trade['sl']

    # 1. الهدف الأول (TP1)
    if tp1_reached and pnl_pct > 0 and not tp2_reached and not sl_hit and not trade.get('trade_closed', False):
        if not trade.get('tp1_hit', False):
            tp1_gain_pct = abs((trade['tp1'] - trade['entry']) / trade['entry']) * 100
            st.session_state.realized_pnl += (tp1_gain_pct * 0.5)
            trade['tp1_hit'] = True
            trade['sl'] = trade['entry']
            save_data()

    # 2. إغلاق أوتوماتيك + تثبيت السعر لحظة ضرب الهدف الثاني أو الوقف
    if (tp2_reached and pnl_pct > 0 or sl_hit) and not trade.get('trade_closed', False):
        close_dt = datetime.now()
        trade['close_time_str'] = close_dt.strftime('%Y-%m-%d %I:%M:%S %p')
        trade['fixed_close_price'] = live_price
        
        if tp2_reached:
            if not trade.get('tp2_hit', False):
                if not trade.get('tp1_hit', False):
                    tp1_gain_pct = abs((trade['tp1'] - trade['entry']) / trade['entry']) * 100
                    st.session_state.realized_pnl += (tp1_gain_pct * 0.5)
                tp2_full_pct = abs((trade['tp2'] - trade['entry']) / trade['entry']) * 100
                st.session_state.realized_pnl += (tp2_full_pct * 0.5)
                trade['tp2_hit'] = True
            trade['close_reason'] = "🚀 Target 2 Hit (Won)"
        else:
            effective_sl_pnl = 0.0 if trade.get('tp1_hit', False) else pnl_pct
            if effective_sl_pnl < 0:
                st.session_state.realized_pnl += effective_sl_pnl
            trade['close_reason'] = "🛑 Stop Loss Hit"

        trade['trade_closed'] = True
        
        if side == 'BUY':
            trade['fixed_pnl_pct'] = ((trade['fixed_close_price'] - trade['entry']) / trade['entry']) * 100
        else:
            trade['fixed_pnl_pct'] = ((trade['entry'] - trade['fixed_close_price']) / trade['entry']) * 100

        # تفعيل فترة الراحة فوراً لحظة الإغلاق الأوتوماتيكي
        st.session_state.cooldowns[sym] = time.time() + (60 * 60)
        save_data()

    if trade.get('trade_closed', False):
        display_price = trade['fixed_close_price']
        display_pnl = trade['fixed_pnl_pct']
        pnl_color_box = "#00ff00" if display_pnl >= 0 else "#ff4b4b"
        pnl_text_box = f"<span style='color:{pnl_color_box}'><b>{display_pnl:.2f}%</b></span>"
        header_title = f"🔴 CLOSE TRADING: {sym} | {side_badge} | {trade['close_reason']} | PnL: {display_pnl:.2f}%"
    else:
        display_price = live_price
        display_pnl = pnl_pct
        header_title = f"{sym} | {side_badge} | {trade['mode']} | PnL: {display_pnl:.2f}%"

    with st.expander(header_title, expanded=True):
        close_info_markdown = f"""
        - **Type / Side:** {side_badge}
        - **Mode:** {trade['mode']}
        - **Entry Price:** ${trade['entry']:.4f}
        - **{"Fixed Close Price" if trade.get('trade_closed', False) else "Live Price"}:** ${display_price:.4f}
        - **Final PnL:** {pnl_text_box if trade.get('trade_closed', False) else pnl_text}
        - **🕒 Open Time:** {trade.get('open_time', 'N/A')}
        - **📤 Close Time:** {trade.get('close_time_str', 'Still Active')}
        - **⏳ Running Duration:** {current_duration}
        - **🎯 Target 1 (50%):** ${trade['tp1']:.4f} {"(✅ Target 1 Hit & Secured)" if trade.get('tp1_hit') else ""}
        - **🚀 Target 2 (50%):** ${trade['tp2']:.4f} {"(🚀 Target 2 Hit / Won)" if trade.get('tp2_hit') else ""}
        - <span style='color:#ff4b4b'>**🛑 Stop Loss:** ${trade['sl']:.4f}</span>
        """
        st.markdown(close_info_markdown, unsafe_allow_html=True)
        
        st.markdown("---")
        if st.button(f"Remove {sym} (Manual)", key=f"remove_active_{sym}"):
            close_dt = datetime.now()
            close_time_str = trade.get('close_time_str', close_dt.strftime('%Y-%m-%d %I:%M:%S %p'))
            duration_sec = (time.time() - open_ts) if trade.get('open_timestamp') else 0
            
            final_record_pnl = trade.get('fixed_pnl_pct', pnl_pct)
            if trade.get('open_time', 'N/A') != 'N/A' and not trade.get('trade_closed', False):
                if not trade.get('tp1_hit', False) and not trade.get('tp2_hit', False):
                    st.session_state.realized_pnl += final_record_pnl
            
            reason_suffix = trade.get('close_reason', 'Manual Close')
            closed_trade_record = {
                'symbol': sym,
                'side': side,
                'mode': trade['mode'] + f" ({reason_suffix})",
                'entry': trade['entry'],
                'close_price': display_price,
                'final_pnl': final_record_pnl,
                'open_time': trade.get('open_time', 'N/A'),
                'close_time': close_time_str,
                'duration': format_duration(duration_sec) if duration_sec > 0 else 'N/A'
            }
            st.session_state.closed_trades.append(closed_trade_record)
            
            # --- تعديل ذكي: لو الصفقة لم تكن قد أُغلقت أوتوماتيك (إغلاق يدوي), نفعل الراحة الآن. أما لو كانت مغلقة أصلاً فلا نجدد العداد ---
            if not trade.get('trade_closed', False):
                st.session_state.cooldowns[sym] = time.time() + (60 * 60)
            
            del st.session_state.active_trades[sym]
            save_data()
            st.rerun()

st.markdown("---")

# ==========================================
# 6. أرشيف الصفقات المغلقة (Closed Trades History)
# ==========================================
st.subheader("📁 Closed Trades History & Timestamps Archive")
if not st.session_state.closed_trades:
    st.info("No closed trades in history yet.")
else:
    for idx, ct in enumerate(reversed(list(st.session_state.closed_trades))):
        original_index = len(st.session_state.closed_trades) - 1 - idx
        pnl_color = "#00ff00" if ct['final_pnl'] >= 0 else "#ff4b4b"
        
        with st.expander(f"Closed: {ct['symbol']} | {ct['side']} | PnL: {ct['final_pnl']:.2f}%"):
            st.markdown(f"""
            - **Side:** {ct['side']}
            - **Mode:** {ct['mode']}
            - **Entry Price:** ${ct['entry']:.4f}
            - **Close Price:** ${ct['close_price']:.4f}
            - **Final PnL:** <span style='color:{pnl_color}'><b>{ct['final_pnl']:.2f}%</b></span>
            - **📥 Opened At:** {ct['open_time']}
            - **📤 Closed At:** {ct['close_time']}
            - **⏱️ Total Duration:** {ct['duration']}
            """, unsafe_allow_html=True)
            
            st.markdown("---")
            if st.button(f"Remove from History", key=f"remove_closed_{original_index}"):
                st.session_state.closed_trades.pop(original_index)
                save_data()
                st.rerun()

st.markdown("---")

# ==========================================
# 7. رادار السوق ولوب فحص الفرص
# ==========================================
st.markdown("### 📡 Market Radar (Live Scanner)")
market_radar_data = []

current_time_epoch = time.time()

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
        if st.session_state.active_trades[symbol].get('trade_closed', False) or (symbol in st.session_state.cooldowns and current_time_epoch < st.session_state.cooldowns[symbol]):
            if symbol in st.session_state.cooldowns and current_time_epoch < st.session_state.cooldowns[symbol]:
                remaining_mins = int((st.session_state.cooldowns[symbol] - current_time_epoch) // 60)
                status = f"🛌 Resting ({remaining_mins}m left)"
            else:
                status = "🔒 Closed / Resting"
        else:
            status = "🟢 Active Trade"
    elif symbol in st.session_state.cooldowns and current_time_epoch < st.session_state.cooldowns[symbol]:
        remaining_mins = int((st.session_state.cooldowns[symbol] - current_time_epoch) // 60)
        status = f"🛌 Resting ({remaining_mins}m left)"
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
    if symbol in st.session_state.cooldowns and current_time_epoch < st.session_state.cooldowns[symbol]:
        continue

    effective_atr_15m = atr_15m if atr_15m > 0 else (current_price * 0.01)
    now_str = datetime.now().strftime('%Y-%m-%d %I:%M:%S %p')

    # 1. إشارات Pro الفورية
    if signal_1h in ['BUY', 'SELL']:
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
                'open_time': now_str,
                'open_timestamp': time.time(),
                'tp1_hit': False,
                'tp2_hit': False,
                'trade_closed': False
            }
            save_data()
            st.rerun()
        except Exception as e:
            st.error(f"Error placing Pro Instant order: {e}")

    # 2. صفقات Action الفورية
    elif signal_15m in ['BUY', 'SELL']:
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
                'open_time': now_str,
                'open_timestamp': time.time(),
                'tp1_hit': False,
                'tp2_hit': False,
                'trade_closed': False
            }
            save_data()
            st.rerun()
        except Exception as e:
            st.error(f"Error placing Action order: {e}")

st.dataframe(market_radar_data, use_container_width=True)
