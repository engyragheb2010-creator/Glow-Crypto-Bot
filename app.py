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
st.title("🤖 SMC Sniper Bot - 10 Symbols & ADX Protected")

# تحديث كل 15 ثانية لمتابعة السعر الحي والتارجت بسرعة
st_autorefresh(interval=15000, limit=None, key="auto_refresh")

if st.button("🔄 Force Update Price / Refresh Now"):
    st.rerun()

# ==========================================
# 2. إعدادات العملات والذاكرة الدائمة (JSON)
# ==========================================
SYMBOLS = ['BTC/USDT', 'ETH/USDT', 'BNB/USDT', 'SOL/USDT', 'LINK/USDT', 'NEAR/USDT', 'SUI/USDT', 'AVAX/USDT', 'ADA/USDT', 'XRP/USDT']
MAX_ACTIVE_TRADES = 3  # أقصى عدد صفقات مفتوحة في نفس الوقت لاختبار الفلتر بأمان
DATA_FILE = 'trades_data.json'

def load_data():
    if os.path.exists(DATA_FILE):
        try:
            with open(DATA_FILE, 'r', encoding='utf-8') as f:
                data = json.load(f)
                if 'realized_pnl' not in data:
                    data['realized_pnl'] = 20.0
                return data
        except:
            return {'active_trades': {}, 'closed_trades': [], 'cooldowns': {}, 'realized_pnl': 20.0}
    return {'active_trades': {}, 'closed_trades': [], 'cooldowns': {}, 'realized_pnl': 20.0}

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
    
    loaded_pnl = saved_data.get('realized_pnl', 20.0)
    st.session_state.realized_pnl = loaded_pnl if loaded_pnl != 0.0 else 20.0
    st.session_state.data_loaded = True

# ==========================================
# 3. الاتصال بمنصة OKX (مع الكاش لتوفير الرامات)
# ==========================================
@st.cache_resource
def get_exchange():
    return ccxt.okx({'enableRateLimit': True})

try:
    exchange = get_exchange()
except Exception as e:
    st.error(f"Error connecting to OKX: {e}")

# ==========================================
# 4. دوال التحليل الفني (مع كاش دقيقتين وفلتر ADX)
# ==========================================
@st.cache_data(ttl=120)
def fetch_data(symbol, timeframe, limit=250):
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

        ema200_series = ta.ema(df['close'], length=200)
        df['EMA200'] = ema200_series if ema200_series is not None and not ema200_series.empty else df['close']

        rsi_series = ta.rsi(df['close'], length=14)
        df['RSI'] = rsi_series if rsi_series is not None and not rsi_series.empty else 50.0

        # إضافة مؤشر ADX لفلترة السوق العرضي (الويك إند)
        adx_df = ta.adx(df['high'], df['low'], df['close'], length=14)
        if adx_df is not None and 'ADX_14' in adx_df.columns:
            df['ADX'] = adx_df['ADX_14']
        else:
            df['ADX'] = 0.0
            
        return df
    except Exception:
        return None

def analyze_smc(df):
    if df is None or len(df) < 200:
        return 'NONE', 0.0

    # فحص آخر شمعة أغلقت فعلياً (-2) لمنع الذيول الوهمية
    closed_candle = df['close'].iloc[-2]
    prev_high = df['high'].iloc[-3]
    prev_low = df['low'].iloc[-3]
    
    raw_atr = df['ATR'].iloc[-2] if 'ATR' in df.columns else 0.0
    atr_value = float(raw_atr) if (raw_atr is not None and not pd.isna(raw_atr)) else 0.0
    
    ema_50 = df['EMA50'].iloc[-2] if 'EMA50' in df.columns else closed_candle
    ema_200 = df['EMA200'].iloc[-2] if 'EMA200' in df.columns else closed_candle
    rsi = df['RSI'].iloc[-2] if 'RSI' in df.columns else 50.0
    
    raw_adx = df['ADX'].iloc[-2] if 'ADX' in df.columns else 0.0
    adx = float(raw_adx) if (raw_adx is not None and not pd.isna(raw_adx)) else 0.0

    # منع الدخول تماماً لو السوق عرضي أو ميت (ADX <= 20)
    if adx <= 20:
        return 'NONE', 0.0
    
    # شراء: ترند صاعد حقيقي + إغلاق فوق القمة السابقة + RSI آمن + زخم ADX > 20
    if ema_50 > ema_200 and closed_candle > ema_50 and closed_candle > prev_high and 50 < rsi < 68:
        return 'BUY', atr_value
    # بيع: ترند هابط حقيقي + إغلاق تحت القاع السابق + RSI آمن + زخم ADX > 20
    elif ema_50 < ema_200 and closed_candle < ema_50 and closed_candle < prev_low and 32 < rsi < 50:
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
# الشريط الجانبي (المحفظة وإعدادات التصفير)
# ==========================================
pnl_color_sidebar = "#00ff00" if st.session_state.realized_pnl >= 0 else "#ff4b4b"
st.sidebar.markdown("### 💰 Portfolio Balance")
st.sidebar.markdown(f"<h2 style='color:{pnl_color_sidebar}; margin-top:-15px;'>${st.session_state.realized_pnl:.2f}</h2>", unsafe_allow_html=True)

st.sidebar.markdown("---")
st.sidebar.markdown("### ⚙️ Portfolio Reset Control")
new_starting_balance = st.sidebar.number_input("Set Starting Capital ($):", min_value=1.0, value=20.0, step=1.0)

if st.sidebar.button("🔄 Reset Portfolio & Clean All"):
    st.session_state.realized_pnl = new_starting_balance
    st.session_state.active_trades = {}
    st.session_state.closed_trades = []
    st.session_state.cooldowns = {}
    save_data()
    st.sidebar.success("Portfolio reset successfully!")
    st.rerun()

# ==========================================
# 5. صفقات التداول النشطة
# ==========================================
st.subheader("📊 Live Market Scanner & Active Portfolio")

st.markdown(f"### 🟢 Active Trades (Max Open: {MAX_ACTIVE_TRADES})")
if not st.session_state.active_trades:
    st.info("No active trades yet. Scanning for strong trending signals (ADX > 20)...")
    
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

    # 2. الإغلاق الأوتوماتيك (TP2 أو Stop Loss)
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
            trade['fixed_pnl_pct'] = tp2_full_pct
        else:
            effective_sl_pnl = 0.0 if trade.get('tp1_hit', False) else pnl_pct
            st.session_state.realized_pnl += effective_sl_pnl
            trade['close_reason'] = "🛑 Stop Loss Hit"
            trade['fixed_pnl_pct'] = effective_sl_pnl

        trade['trade_closed'] = True
        st.session_state.cooldowns[sym] = time.time() + (60 * 60)
        save_data()

    is_closed = trade.get('trade_closed', False) or trade.get('resting_activated', False) or ('close_reason' in trade)
    
    if is_closed:
        display_price = trade.get('fixed_close_price', live_price)
        display_pnl = trade.get('fixed_pnl_pct', pnl_pct)
        pnl_color_box = "#00ff00" if display_pnl >= 0 else "#ff4b4b"
        pnl_text_box = f"<span style='color:{pnl_color_box}'><b>{display_pnl:.2f}%</b></span>"
        c_reason = trade.get('close_reason', 'Closed')
        header_title = f"🔴 CLOSE TRADING: {sym} | {side_badge} | {c_reason} | PnL: {display_pnl:.2f}%"
    else:
        display_price = live_price
        display_pnl = pnl_pct
        header_title = f"{sym} | {side_badge} | {trade['mode']} | PnL: {display_pnl:.2f}%"

    with st.expander(header_title, expanded=True):
        close_info_markdown = f"""
        - **Type / Side:** {side_badge}
        - **Mode:** {trade['mode']}
        - **Entry Price:** ${trade['entry']:.4f}
        - **{"Fixed Close Price" if is_closed else "Live Price"}:** ${display_price:.4f}
        - **Final PnL:** {pnl_text_box if is_closed else pnl_text}
        - **🕒 Open Time:** {trade.get('open_time', 'N/A')}
        - **📤 Close Time:** {trade.get('close_time_str', 'Still Active')}
        - **⏳ Running Duration:** {current_duration}
        - **🎯 Target 1 (50%):** ${trade['tp1']:.4f} {"(✅ Target 1 Hit & Secured)" if trade.get('tp1_hit') else ""}
        - **🚀 Target 2 (50%):** ${trade['tp2']:.4f} {"(🚀 Target 2 Hit / Won)" if trade.get('tp2_hit') else ""}
        
