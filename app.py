import streamlit as st
import ccxt
import pandas as pd
import pandas_ta as ta
import requests
import time
import json
import os
from datetime import datetime

# ==========================================
# 1. إعدادات الشاشة والربط السحابي (JSONBin)
# ==========================================
st.set_page_config(page_title="SMC Sniper Bot - Futures Dual Mode", layout="wide")
st.title("🤖 SMC Sniper Bot — 🐢 Swing vs ⚡ Pro Scalping (Futures)")

# حطي الكودين بتوعك من موقع jsonbin.io هنا بين علامات التنصيص:
JSONBIN_BIN_ID = "6b02bc93ffd5d16053d55d5d"
JSONBIN_API_KEY = "$2a$10$Y2gG93ZSPm0TetpeSZzUJOjJejPRL42P17olP0s3edOSXMlmWCkFi"

# ==========================================
# 2. إعدادات العملات والعمولة والذاكرة السحابية
# ==========================================
SYMBOLS = ['BTC/USDT', 'ETH/USDT', 'BNB/USDT', 'SOL/USDT', 'LINK/USDT', 'NEAR/USDT', 'SUI/USDT', 'AVAX/USDT', 'ADA/USDT', 'XRP/USDT']
MAX_ACTIVE_TRADES = 10
DATA_FILE = 'trades_data_dual.json'
OKX_ROUND_TRIP_FEE = 0.001  # 0.05% دخول + 0.05% خروج (Taker Fee على OKX Futures)

def get_default_strategy_state(start_balance=20.0):
    return {
        'active_trades': {},
        'closed_trades': [],
        'cooldowns': {},
        'realized_pnl': start_balance
    }

def get_default_data():
    return {
        'swing': get_default_strategy_state(20.0),
        'scalping': get_default_strategy_state(20.0)
    }

def is_cloud_configured():
    return (
        JSONBIN_BIN_ID and "حطي" not in JSONBIN_BIN_ID
        and JSONBIN_API_KEY and "حطي" not in JSONBIN_API_KEY
    )

def normalize_data(raw_data):
    default = get_default_data()
    if not isinstance(raw_data, dict):
        return default
    if 'swing' in raw_data and 'scalping' in raw_data:
        for key in ['swing', 'scalping']:
            for field, val in get_default_strategy_state().items():
                if field not in raw_data[key]:
                    raw_data[key][field] = val
        return raw_data
    if 'active_trades' in raw_data:
        default['swing'] = {
            'active_trades': raw_data.get('active_trades', {}),
            'closed_trades': raw_data.get('closed_trades', []),
            'cooldowns': raw_data.get('cooldowns', {}),
            'realized_pnl': raw_data.get('realized_pnl', 20.0)
        }
    return default

def load_data():
    if is_cloud_configured():
        try:
            url = f"https://api.jsonbin.io/v3/b/{JSONBIN_BIN_ID}/latest"
            headers = {"X-Master-Key": JSONBIN_API_KEY}
            res = requests.get(url, headers=headers, timeout=10)
            if res.status_code == 200:
                return normalize_data(res.json().get("record", {}))
        except Exception as e:
            st.warning(f"Cloud load warning: {e}")

    if os.path.exists(DATA_FILE):
        try:
            with open(DATA_FILE, 'r', encoding='utf-8') as f:
                return normalize_data(json.load(f))
        except:
            return get_default_data()
    return get_default_data()

def save_data():
    data = st.session_state.bot_data
    try:
        with open(DATA_FILE, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=4)
    except Exception:
        pass

    if is_cloud_configured():
        try:
            url = f"https://api.jsonbin.io/v3/b/{JSONBIN_BIN_ID}"
            headers = {
                "Content-Type": "application/json",
                "X-Master-Key": JSONBIN_API_KEY
            }
            requests.put(url, json=data, headers=headers, timeout=10)
        except Exception as e:
            st.warning(f"Cloud save warning: {e}")

if 'data_loaded' not in st.session_state:
    st.session_state.bot_data = load_data()
    st.session_state.data_loaded = True

# ==========================================
# 3. الاتصال بمنصة OKX
# ==========================================
@st.cache_resource
def get_exchange():
    return ccxt.okx({'enableRateLimit': True})

try:
    exchange = get_exchange()
except Exception as e:
    st.error(f"Error connecting to OKX: {e}")

# ==========================================
# 4. دوال جلب البيانات والمؤشرات
# ==========================================
def _build_df(symbol, timeframe, limit=250):
    try:
        bars = exchange.fetch_ohlcv(symbol, timeframe, limit=limit)
        df = pd.DataFrame(bars, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
        for col in ['open', 'high', 'low', 'close', 'volume']:
            df[col] = pd.to_numeric(df[col], errors='coerce')

        atr_s = ta.atr(df['high'], df['low'], df['close'], length=14)
        df['ATR'] = atr_s if atr_s is not None and not atr_s.empty else 0.0

        ema9_s = ta.ema(df['close'], length=9)
        df['EMA9'] = ema9_s if ema9_s is not None and not ema9_s.empty else df['close']

        ema21_s = ta.ema(df['close'], length=21)
        df['EMA21'] = ema21_s if ema21_s is not None and not ema21_s.empty else df['close']

        ema50_s = ta.ema(df['close'], length=50)
        df['EMA50'] = ema50_s if ema50_s is not None and not ema50_s.empty else df['close']

        ema200_s = ta.ema(df['close'], length=200)
        df['EMA200'] = ema200_s if ema200_s is not None and not ema200_s.empty else df['close']

        rsi_s = ta.rsi(df['close'], length=14)
        df['RSI'] = rsi_s if rsi_s is not None and not rsi_s.empty else 50.0

        adx_df = ta.adx(df['high'], df['low'], df['close'], length=14)
        df['ADX'] = adx_df['ADX_14'] if (adx_df is not None and 'ADX_14' in adx_df.columns) else 0.0

        df['VOL_MA20'] = df['volume'].rolling(20).mean().fillna(df['volume'])

        dt_series = pd.to_datetime(df['timestamp'], unit='ms').dt.date
        tp = (df['high'] + df['low'] + df['close']) / 3.0
        pv = tp * df['volume']
        cum_pv = pv.groupby(dt_series).cumsum()
        cum_v = df['volume'].groupby(dt_series).cumsum().replace(0, pd.NA)
        df['VWAP'] = (cum_pv / cum_v).fillna(df['close'])

        return df
    except Exception:
        return None

@st.cache_data(ttl=120)
def fetch_data_slow(symbol, timeframe, limit=250):
    return _build_df(symbol, timeframe, limit)

@st.cache_data(ttl=30)
def fetch_data_fast(symbol, timeframe, limit=250):
    return _build_df(symbol, timeframe, limit)

def analyze_smc(df, adx_min=20, rsi_buy=(50, 68), rsi_sell=(32, 50)):
    if df is None or len(df) < 200:
        return 'NONE', 0.0

    closed_candle = df['close'].iloc[-2]
    prev_high = df['high'].iloc[-3]
    prev_low = df['low'].iloc[-3]

    raw_atr = df['ATR'].iloc[-2]
    atr_val = float(raw_atr) if (raw_atr is not None and not pd.isna(raw_atr)) else 0.0

    ema_50 = df['EMA50'].iloc[-2]
    ema_200 = df['EMA200'].iloc[-2]
    rsi = df['RSI'].iloc[-2]

    raw_adx = df['ADX'].iloc[-2]
    adx = float(raw_adx) if (raw_adx is not None and not pd.isna(raw_adx)) else 0.0

    if adx <= adx_min:
        return 'NONE', 0.0

    if ema_50 > ema_200 and closed_candle > ema_50 and closed_candle > prev_high and rsi_buy[0] < rsi < rsi_buy[1]:
        return 'BUY', atr_val
    elif ema_50 < ema_200 and closed_candle < ema_50 and closed_candle < prev_low and rsi_sell[0] < rsi < rsi_sell[1]:
        return 'SELL', atr_val

    return 'NONE', 0.0

def analyze_scalping(df_5m, df_15m):
    if df_5m is None or df_15m is None or len(df_5m) < 50 or len(df_15m) < 50:
        return 'NONE', 0.0, "⏳ Loading Data"

    trend_15m_up = df_15m['close'].iloc[-2] > df_15m['EMA50'].iloc[-2]
    trend_15m_down = df_15m['close'].iloc[-2] < df_15m['EMA50'].iloc[-2]

    o = df_5m['open'].iloc[-2]
    h = df_5m['high'].iloc[-2]
    l = df_5m['low'].iloc[-2]
    c = df_5m['close'].iloc[-2]
    v = df_5m['volume'].iloc[-2]
    vol_ma = df_5m['VOL_MA20'].iloc[-2]

    ema9 = df_5m['EMA9'].iloc[-2]
    ema21 = df_5m['EMA21'].iloc[-2]
    vwap = df_5m['VWAP'].iloc[-2]
    rsi = df_5m['RSI'].iloc[-2]
    raw_atr = df_5m['ATR'].iloc[-2]
    atr_val = float(raw_atr) if (raw_atr is not None and not pd.isna(raw_atr)) else 0.0

    vol_ok = v > (vol_ma * 1.3)

    if trend_15m_up:
        if c <= vwap:
            return 'NONE', atr_val, "⏳ Wait Close > VWAP"
        if ema9 <= ema21:
            return 'NONE', atr_val, "⏳ Wait EMA9 > EMA21"
        if not (l <= ema9 * 1.001 and c > ema9 and c > o):
            return 'NONE', atr_val, "⏳ Wait Pullback to EMA9"
        if not vol_ok:
            return 'NONE', atr_val, "⏳ Wait Volume Spike"
        if not (45 < rsi < 70):
            return 'NONE', atr_val, "⏳ Wait RSI (45-70)"
        return 'BUY', atr_val, "👀 Ready (BUY Pullback)"
    elif trend_15m_down:
        if c >= vwap:
            return 'NONE', atr_val, "⏳ Wait Close < VWAP"
        if ema9 >= ema21:
            return 'NONE', atr_val, "⏳ Wait EMA9 < EMA21"
        if not (h >= ema9 * 0.999 and c < ema9 and c < o):
            return 'NONE', atr_val, "⏳ Wait Pullback to EMA9"
        if not vol_ok:
            return 'NONE', atr_val, "⏳ Wait Volume Spike"
        if not (30 < rsi < 55):
            return 'NONE', atr_val, "⏳ Wait RSI (30-55)"
        return 'SELL', atr_val, "👀 Ready (SELL Pullback)"

    return 'NONE', atr_val, "😴 Neutral 15m"

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
    return f"{mins} mins"

def calc_stats(state):
    closed = state['closed_trades']
    total = len(closed)
    wins = sum(1 for t in closed if t.get('net_pnl_usd', t.get('final_pnl', 0)) > 0)
    win_rate = (wins / total * 100) if total > 0 else 0.0
    active_count = sum(1 for t in state['active_trades'].values() if not t.get('trade_closed', False))
    return total, wins, win_rate, active_count

# ==========================================
# 5. الشريط الجانبي (إعدادات الفيوتشر والتصفير)
# ==========================================
st.sidebar.markdown("### ⚙️ Futures Settings")
if is_cloud_configured():
    st.sidebar.success("☁️ Cloud Memory: Connected")
else:
    st.sidebar.warning("⚠️ Cloud Memory: Not Connected")

st.sidebar.caption("💸 OKX Futures Fee: 0.10% (0.05% In + 0.05% Out) auto-deducted")

st.sidebar.markdown("#### 🐢 Swing Futures")
swing_margin = st.sidebar.number_input("Swing Margin / Trade ($):", min_value=1.0, value=5.0, step=1.0)
swing_leverage = st.sidebar.slider("Swing Leverage (x):", min_value=1, max_value=20, value=3)
st.sidebar.caption(f"Position Size: **${swing_margin * swing_leverage:.0f}** | Est. Fee: **${swing_margin * swing_leverage * OKX_ROUND_TRIP_FEE:.3f}**")

st.sidebar.markdown("#### ⚡ Scalping Futures")
scalp_margin = st.sidebar.number_input("Scalping Margin / Trade ($):", min_value=1.0, value=5.0, step=1.0)
scalp_leverage = st.sidebar.slider("Scalping Leverage (x):", min_value=1, max_value=20, value=5)
st.sidebar.caption(f"Position Size: **${scalp_margin * scalp_leverage:.0f}** | Est. Fee: **${scalp_margin * scalp_leverage * OKX_ROUND_TRIP_FEE:.3f}**")

st.sidebar.markdown("---")
new_cap = st.sidebar.number_input("Starting Capital per Mode ($):", min_value=1.0, value=20.0, step=1.0)

if st.sidebar.button("🔄 Reset BOTH (Swing + Scalping)"):
    st.session_state.bot_data = {
        'swing': get_default_strategy_state(new_cap),
        'scalping': get_default_strategy_state(new_cap)
    }
    save_data()
    st.sidebar.success("Both portfolios reset!")
    st.rerun()

col_r1, col_r2 = st.sidebar.columns(2)
with col_r1:
    if st.button("Reset Swing"):
        st.session_state.bot_data['swing'] = get_default_strategy_state(new_cap)
        save_data()
        st.rerun()
with col_r2:
    if st.button("Reset Scalping"):
        st.session_state.bot_data['scalping'] = get_default_strategy_state(new_cap)
        save_data()
        st.rerun()

# ==========================================
# 6. محرك التحديث والرادار (مع حساب الفيوتشر والعمولة)
# ==========================================
def update_active_trades(state, live_prices, cooldown_mins, default_margin, default_lev):
    changed = False
    for sym, trade in list(state['active_trades'].items()):
        live_price = live_prices.get(sym, trade['entry'])
        side = trade.get('side', 'BUY')
        margin = trade.get('margin', default_margin)
        lev = trade.get('leverage', default_lev)
        pos_size = margin * lev

        if side == 'BUY':
            price_pnl_pct = ((live_price - trade['entry']) / trade['entry']) * 100
            tp2_reached = live_price >= trade['tp2']
            tp1_reached = live_price >= trade['tp1']
            sl_hit = live_price <= trade['sl']
        else:
            price_pnl_pct = ((trade['entry'] - live_price) / trade['entry']) * 100
            tp2_reached = live_price <= trade['tp2']
            tp1_reached = live_price <= trade['tp1']
            sl_hit = live_price >= trade['sl']

        # TP1 (إغلاق 50% من الصفقة وخصم عمولة النصف ده)
        if tp1_reached and price_pnl_pct > 0 and not tp2_reached and not sl_hit and not trade.get('trade_closed', False):
            if not trade.get('tp1_hit', False):
                tp1_pct = abs((trade['tp1'] - trade['entry']) / trade['entry']) * 100
                half_size = pos_size * 0.5
                gross_usd = half_size * (tp1_pct / 100.0)
                fee_usd = half_size * OKX_ROUND_TRIP_FEE
                net_tp1_usd = gross_usd - fee_usd

                state['realized_pnl'] += net_tp1_usd
                trade['tp1_realized_usd'] = net_tp1_usd
                trade['tp1_hit'] = True
                trade['sl'] = trade['entry']
                changed = True

        # TP2 أو SL
        if (tp2_reached and price_pnl_pct > 0 or sl_hit) and not trade.get('trade_closed', False):
            trade['close_time_str'] = datetime.now().strftime('%Y-%m-%d %I:%M:%S %p')
            trade['fixed_close_price'] = live_price

            if tp2_reached:
                tp1_usd = trade.get('tp1_realized_usd', 0.0)
                if not trade.get('tp1_hit', False):
                    tp1_pct = abs((trade['tp1'] - trade['entry']) / trade['entry']) * 100
                    half_size = pos_size * 0.5
                    tp1_usd = (half_size * (tp1_pct / 100.0)) - (half_size * OKX_ROUND_TRIP_FEE)
                    state['realized_pnl'] += tp1_usd
                    trade['tp1_realized_usd'] = tp1_usd
                    trade['tp1_hit'] = True

                tp2_pct = abs((trade['tp2'] - trade['entry']) / trade['entry']) * 100
                half_size = pos_size * 0.5
                tp2_usd = (half_size * (tp2_pct / 100.0)) - (half_size * OKX_ROUND_TRIP_FEE)
                state['realized_pnl'] += tp2_usd
                trade['tp2_hit'] = True

                total_net_usd = tp1_usd + tp2_usd
                trade['close_reason'] = "🚀 Target 2 Hit (Won)"
                trade['fixed_net_usd'] = total_net_usd
                trade['fixed_roi_pct'] = (total_net_usd / margin) * 100.0
            else:
                if trade.get('tp1_hit', False):
                    # النصف الأول كسب TP1، والنصف التاني قفل عند نقطة الدخول (خسارة عمولة النصف التاني بس)
                    half_fee = (pos_size * 0.5) * OKX_ROUND_TRIP_FEE
                    state['realized_pnl'] -= half_fee
                    total_net_usd = trade.get('tp1_realized_usd', 0.0) - half_fee
                    trade['close_reason'] = "🛡️ Breakeven SL (TP1 Secured)"
                else:
                    gross_usd = pos_size * (price_pnl_pct / 100.0)
                    fee_usd = pos_size * OKX_ROUND_TRIP_FEE
                    total_net_usd = gross_usd - fee_usd
                    state['realized_pnl'] += total_net_usd
                    trade['close_reason'] = "🛑 Stop Loss Hit"

                trade['fixed_net_usd'] = total_net_usd
                trade['fixed_roi_pct'] = (total_net_usd / margin) * 100.0

            trade['trade_closed'] = True
            state['cooldowns'][sym] = time.time() + (cooldown_mins * 60)
            changed = True

    return changed

def scan_swing(state, config, dfs_cache, margin, leverage):
    radar_rows = []
    now_epoch = time.time()
    changed = False

    htf, ltf = config['htf'], config['ltf']
    adx_min = config['adx_min']
    rsi_buy, rsi_sell = config['rsi_buy'], config['rsi_sell']

    for sym in SYMBOLS:
        df_htf = dfs_cache.get((sym, htf))
        df_ltf = dfs_cache.get((sym, ltf))
        if df_htf is None or df_ltf is None:
            continue

        current_price = df_ltf['close'].iloc[-1]
        sig_htf, _ = analyze_smc(df_htf, adx_min=adx_min, rsi_buy=rsi_buy, rsi_sell=rsi_sell)
        sig_ltf, _ = analyze_smc(df_ltf, adx_min=adx_min, rsi_buy=rsi_buy, rsi_sell=rsi_sell)
        vol_ltf = df_ltf['volume'].iloc[-1]

        raw_atr = df_ltf['ATR'].iloc[-2]
        atr_val = float(raw_atr) if (raw_atr is not None and not pd.isna(raw_atr)) else 0.0
        raw_adx = df_ltf['ADX'].iloc[-2]
        adx_val = float(raw_adx) if (raw_adx is not None and not pd.isna(raw_adx)) else 0.0
        raw_rsi = df_ltf['RSI'].iloc[-2]
        rsi_val = float(raw_rsi) if (raw_rsi is not None and not pd.isna(raw_rsi)) else 50.0

        trend_htf_up = df_htf['close'].iloc[-2] > df_htf['EMA200'].iloc[-2]
        trend_htf_down = df_htf['close'].iloc[-2] < df_htf['EMA200'].iloc[-2]
        ema50 = df_ltf['EMA50'].iloc[-2]
        ema200 = df_ltf['EMA200'].iloc[-2]
        closed_ltf = df_ltf['close'].iloc[-2]
        prev_high = df_ltf['high'].iloc[-3]
        prev_low = df_ltf['low'].iloc[-3]

        open_count = sum(1 for t in state['active_trades'].values() if not t.get('trade_closed', False))

        if sym in state['active_trades']:
            t_obj = state['active_trades'][sym]
            if t_obj.get('trade_closed', False):
                rem = int((state['cooldowns'].get(sym, 0) - now_epoch) // 60)
                status = f"🛌 Resting ({rem}m left)" if rem > 0 else "🔒 Closed (Ready to Remove)"
            else:
                status = "🟢 Active Trade"
        elif sym in state['cooldowns'] and now_epoch < state['cooldowns'][sym]:
            rem = int((state['cooldowns'][sym] - now_epoch) // 60)
            status = f"🛌 Resting ({rem}m left)"
        elif open_count >= MAX_ACTIVE_TRADES:
            status = "⏸️ Max Trades Reached"
        elif adx_val <= adx_min:
            status = f"😴 Sideways (ADX ≤ {adx_min})"
        else:
            if trend_htf_up:
                if ema50 <= ema200: status = "⏳ Wait 15m EMA50>200 (1h Up)"
                elif not (rsi_buy[0] < rsi_val < rsi_buy[1]): status = f"⏳ Wait RSI {rsi_buy[0]}-{rsi_buy[1]}"
                elif closed_ltf <= ema50: status = "⏳ Wait Close>EMA50"
                elif closed_ltf <= prev_high: status = "⏳ Wait High Breakout"
                else: status = "👀 Ready (BUY)"
            else:
                if ema50 >= ema200: status = "⏳ Wait 15m EMA50<200 (1h Down)"
                elif not (rsi_sell[0] < rsi_val < rsi_sell[1]): status = f"⏳ Wait RSI {rsi_sell[0]}-{rsi_sell[1]}"
                elif closed_ltf >= ema50: status = "⏳ Wait Close<EMA50"
                elif closed_ltf >= prev_low: status = "⏳ Wait Low Breakout"
                else: status = "👀 Ready (SELL)"

        radar_rows.append({
            "🪙 Symbol": sym,
            "💵 Price": f"${current_price:.4f}",
            "💪 15m ADX": f"{adx_val:.1f}",
            "📈 15m RSI": f"{rsi_val:.1f}",
            "📊 Volume": f"{vol_ltf:.1f}",
            "Status": status
        })

        if sym in state['active_trades'] or open_count >= MAX_ACTIVE_TRADES:
            continue
        if sym in state['cooldowns'] and now_epoch < state['cooldowns'][sym]:
            continue

        eff_atr = atr_val if atr_val > 0 else (current_price * 0.01)
        now_str = datetime.now().strftime('%Y-%m-%d %I:%M:%S %p')

        entry_side, mode_label = None, None
        tp1_mult, tp2_mult, sl_mult, min_tp = config['tp1_mult'], config['tp2_mult'], config['sl_mult'], config['min_tp']

        if sig_htf in ['BUY', 'SELL']:
            entry_side = sig_htf
            mode_label = "🎯 Pro (1h)"
            raw_htf_atr = df_htf['ATR'].iloc[-2]
            eff_atr = float(raw_htf_atr) if (raw_htf_atr is not None and not pd.isna(raw_htf_atr) and raw_htf_atr > 0) else (current_price * 0.015)
            tp1_mult, tp2_mult, sl_mult, min_tp = 2.0, 4.0, 2.0, 0.02
        elif (sig_ltf == 'BUY' and trend_htf_up) or (sig_ltf == 'SELL' and trend_htf_down):
            entry_side = sig_ltf
            mode_label = "🐢 Swing (15m)"

        if entry_side:
            if entry_side == 'BUY':
                tp1 = current_price + max(eff_atr * tp1_mult, current_price * min_tp)
                tp2 = current_price + max(eff_atr * tp2_mult, current_price * (min_tp * 2))
                sl = current_price - (eff_atr * sl_mult)
            else:
                tp1 = current_price - max(eff_atr * tp1_mult, current_price * min_tp)
                tp2 = current_price - max(eff_atr * tp2_mult, current_price * (min_tp * 2))
                sl = current_price + (eff_atr * sl_mult)

            state['active_trades'][sym] = {
                'entry': current_price, 'tp1': tp1, 'tp2': tp2, 'sl': sl, 'original_sl': sl,
                'mode': mode_label, 'side': entry_side, 'open_time': now_str,
                'open_timestamp': time.time(), 'tp1_hit': False, 'tp2_hit': False, 'trade_closed': False,
                'margin': margin, 'leverage': leverage
            }
            changed = True

    return radar_rows, changed

def scan_scalping(state, config, dfs_cache, margin, leverage):
    radar_rows = []
    now_epoch = time.time()
    changed = False

    for sym in SYMBOLS:
        df_15m = dfs_cache.get((sym, '15m'))
        df_5m = dfs_cache.get((sym, '5m'))
        if df_15m is None or df_5m is None:
            continue

        current_price = df_5m['close'].iloc[-1]
        sig, atr_val, diag_status = analyze_scalping(df_5m, df_15m)
        rsi_val = float(df_5m['RSI'].iloc[-2]) if not pd.isna(df_5m['RSI'].iloc[-2]) else 50.0
        vwap_val = float(df_5m['VWAP'].iloc[-2])
        vol_ratio = df_5m['volume'].iloc[-2] / max(df_5m['VOL_MA20'].iloc[-2], 1e-9)

        open_count = sum(1 for t in state['active_trades'].values() if not t.get('trade_closed', False))

        if sym in state['active_trades']:
            t_obj = state['active_trades'][sym]
            if t_obj.get('trade_closed', False):
                rem = int((state['cooldowns'].get(sym, 0) - now_epoch) // 60)
                status = f"🛌 Resting ({rem}m left)" if rem > 0 else "🔒 Closed (Ready to Remove)"
            else:
                status = "🟢 Active Trade"
        elif sym in state['cooldowns'] and now_epoch < state['cooldowns'][sym]:
            rem = int((state['cooldowns'][sym] - now_epoch) // 60)
            status = f"🛌 Resting ({rem}m left)"
        elif open_count >= MAX_ACTIVE_TRADES:
            status = "⏸️ Max Trades Reached"
        else:
            status = diag_status

        radar_rows.append({
            "🪙 Symbol": sym,
            "💵 Price": f"${current_price:.4f}",
            "📍 VWAP": f"${vwap_val:.4f}",
            "📈 5m RSI": f"{rsi_val:.1f}",
            "🔥 Vol Ratio": f"{vol_ratio:.2f}x",
            "Status": status
        })

        if sym in state['active_trades'] or open_count >= MAX_ACTIVE_TRADES:
            continue
        if sym in state['cooldowns'] and now_epoch < state['cooldowns'][sym]:
            continue

        if sig in ['BUY', 'SELL']:
            eff_atr = atr_val if atr_val > 0 else (current_price * 0.005)
            now_str = datetime.now().strftime('%Y-%m-%d %I:%M:%S %p')
            tp1_mult, tp2_mult, sl_mult, min_tp = config['tp1_mult'], config['tp2_mult'], config['sl_mult'], config['min_tp']

            if sig == 'BUY':
                tp1 = current_price + max(eff_atr * tp1_mult, current_price * min_tp)
                tp2 = current_price + max(eff_atr * tp2_mult, current_price * (min_tp * 2))
                sl = current_price - max(eff_atr * sl_mult, current_price * 0.004)
            else:
                tp1 = current_price - max(eff_atr * tp1_mult, current_price * min_tp)
                tp2 = current_price - max(eff_atr * tp2_mult, current_price * (min_tp * 2))
                sl = current_price + max(eff_atr * sl_mult, current_price * 0.004)

            state['active_trades'][sym] = {
                'entry': current_price, 'tp1': tp1, 'tp2': tp2, 'sl': sl, 'original_sl': sl,
                'mode': "⚡ Pro Scalp (VWAP+EMA9)", 'side': sig, 'open_time': now_str,
                'open_timestamp': time.time(), 'tp1_hit': False, 'tp2_hit': False, 'trade_closed': False,
                'margin': margin, 'leverage': leverage
            }
            changed = True

    return radar_rows, changed

def render_strategy_tab(strategy_key, state, live_prices, radar_rows, cooldown_mins, default_margin, default_lev):
    st.markdown(f"### 🟢 Active Trades (Max: {MAX_ACTIVE_TRADES})")
    if not state['active_trades']:
        st.info("No active trades right now. Scanning market...")

    for sym, trade in list(state['active_trades'].items()):
        live_price = live_prices.get(sym, trade['entry'])
        side = trade.get('side', 'BUY')
        margin = trade.get('margin', default_margin)
        lev = trade.get('leverage', default_lev)
        pos_size = margin * lev

        price_pnl_pct = ((live_price - trade['entry']) / trade['entry'] * 100) if side == 'BUY' else ((trade['entry'] - live_price) / trade['entry'] * 100)
        est_net_usd = (pos_size * (price_pnl_pct / 100.0)) - (pos_size * OKX_ROUND_TRIP_FEE)
        est_roi_pct = (est_net_usd / margin) * 100.0

        is_closed = trade.get('trade_closed', False)
        display_price = trade.get('fixed_close_price', live_price) if is_closed else live_price
        display_usd = trade.get('fixed_net_usd', est_net_usd) if is_closed else est_net_usd
        display_roi = trade.get('fixed_roi_pct', est_roi_pct) if is_closed else est_roi_pct

        pnl_color = "#00ff00" if display_usd >= 0 else "#ff4b4b"
        side_badge = "🟢 LONG" if side == 'BUY' else "🔴 SHORT"
        open_ts = trade.get('open_timestamp', time.time())
        duration_str = format_duration(time.time() - open_ts) if trade.get('open_timestamp') else "N/A"

        if is_closed:
            header = f"🔴 CLOSED: {sym} | {side_badge} ({lev}x) | {trade.get('close_reason', 'Closed')} | Net: ${display_usd:+.2f} ({display_roi:+.1f}%)"
        else:
            header = f"{sym} | {side_badge} ({lev}x) | Net: ${display_usd:+.2f} ({display_roi:+.1f}%)"

        with st.expander(header, expanded=True):
            tp1_tag = "(✅ TP1 Secured)" if trade.get('tp1_hit') else ""
            tp2_tag = "(🚀 TP2 Won)" if trade.get('tp2_hit') else ""
            st.markdown(f"""
            - **Side:** {side_badge} | **Margin:** ${margin:.2f} × **{lev}x** = **${pos_size:.2f}**
            - **Entry:** ${trade['entry']:.4f} | **{'Close' if is_closed else 'Live'}:** ${display_price:.4f}
            - **Net PnL (After Fees):** <span style='color:{pnl_color}'><b>${display_usd:+.2f} ({display_roi:+.1f}% ROI)</b></span>
            - **🕒 Opened:** {trade.get('open_time', 'N/A')} | **⏳ Duration:** {duration_str}
            - **🎯 TP1 (50%):** ${trade['tp1']:.4f} {tp1_tag}
            - **🚀 TP2 (50%):** ${trade['tp2']:.4f} {tp2_tag}
            - <span style='color:#ff4b4b'>**🛑 SL:** ${trade['sl']:.4f}</span>
            """, unsafe_allow_html=True)

            if st.button(f"Move {sym} to Archive", key=f"rem_act_{strategy_key}_{sym}"):
                close_time_str = trade.get('close_time_str', datetime.now().strftime('%Y-%m-%d %I:%M:%S %p'))
                state['closed_trades'].append({
                    'symbol': sym, 'side': side,
                    'mode': f"{trade['mode']} ({lev}x) - {trade.get('close_reason', 'Manual')}",
                    'entry': trade['entry'], 'close_price': display_price,
                    'net_pnl_usd': display_usd, 'final_pnl': display_roi,
                    'open_time': trade.get('open_time', 'N/A'),
                    'close_time': close_time_str, 'duration': duration_str
                })
                if not is_closed:
                    state['cooldowns'][sym] = time.time() + (cooldown_mins * 60)
                state['active_trades'].pop(sym, None)
                save_data()
                st.rerun()

    st.markdown("---")
    st.markdown("### 📁 Closed Trades History")
    if not state['closed_trades']:
        st.info("No closed trades in archive yet.")
    else:
        for idx, ct in enumerate(reversed(list(state['closed_trades']))):
            orig_idx = len(state['closed_trades']) - 1 - idx
            net_usd = ct.get('net_pnl_usd', 0.0)
            c_color = "#00ff00" if net_usd >= 0 else "#ff4b4b"
            with st.expander(f"Closed: {ct['symbol']} | {ct['side']} | Net: ${net_usd:+.2f} ({ct['final_pnl']:+.1f}%)"):
                st.markdown(f"""
                - **Mode:** {ct['mode']}
                - **Entry:** ${ct['entry']:.4f} → **Close:** ${ct['close_price']:.4f}
                - **Net PnL:** <span style='color:{c_color}'><b>${net_usd:+.2f} ({ct['final_pnl']:+.1f}% ROI)</b></span>
                - **📥 Opened:** {ct['open_time']} | **📤 Closed:** {ct['close_time']} ({ct['duration']})
                """, unsafe_allow_html=True)
                if st.button("Delete Record", key=f"rem_cls_{strategy_key}_{orig_idx}"):
                    state['closed_trades'].pop(orig_idx)
                    save_data()
                    st.rerun()

    st.markdown("---")
    st.markdown("### 📡 Live Market Radar")
    st.dataframe(radar_rows, use_container_width=True)

# ==========================================
# 7. لوحة التحكم الحية (تحديث تلقائي كل 15 ثانية)
# ==========================================
SWING_CONFIG = {
    'htf': '1h', 'ltf': '15m', 'adx_min': 20,
    'rsi_buy': (50, 68), 'rsi_sell': (32, 50),
    'tp1_mult': 1.8, 'tp2_mult': 3.5, 'sl_mult': 1.8, 'min_tp': 0.015,
    'cooldown_mins': 60
}

SCALP_CONFIG = {
    'tp1_mult': 1.2, 'tp2_mult': 2.2, 'sl_mult': 1.4, 'min_tp': 0.005,
    'cooldown_mins': 15
}

@st.fragment(run_every=15)
def live_dashboard():
    col1, col2 = st.columns([1, 2])
    with col1:
        if st.button("🔄 Force Update Now"):
            st.rerun()
    with col2:
        st.caption(f"🕒 Last Auto-Update: {datetime.now().strftime('%I:%M:%S %p')} (Auto-refreshes every 15s)")

    swing_state = st.session_state.bot_data['swing']
    scalp_state = st.session_state.bot_data['scalping']

    needed_tickers = set(swing_state['active_trades'].keys()) | set(scalp_state['active_trades'].keys())
    live_prices = {}
    for sym in needed_tickers:
        try:
            live_prices[sym] = exchange.fetch_ticker(sym)['last']
        except:
            pass

    dfs_cache = {}
    for sym in SYMBOLS:
        dfs_cache[(sym, '1h')] = fetch_data_slow(sym, '1h')
        dfs_cache[(sym, '15m')] = fetch_data_slow(sym, '15m')
        dfs_cache[(sym, '5m')] = fetch_data_fast(sym, '5m')

    c1 = update_active_trades(swing_state, live_prices, SWING_CONFIG['cooldown_mins'], swing_margin, swing_leverage)
    c2 = update_active_trades(scalp_state, live_prices, SCALP_CONFIG['cooldown_mins'], scalp_margin, scalp_leverage)
    swing_radar, c3 = scan_swing(swing_state, SWING_CONFIG, dfs_cache, swing_margin, swing_leverage)
    scalp_radar, c4 = scan_scalping(scalp_state, SCALP_CONFIG, dfs_cache, scalp_margin, scalp_leverage)

    if c1 or c2 or c3 or c4:
        save_data()

    s_tot, s_win, s_wr, s_act = calc_stats(swing_state)
    sc_tot, sc_win, sc_wr, sc_act = calc_stats(scalp_state)

    st.markdown("### 🏆 Live Comparison: Swing vs Pro Scalping (After OKX Fees)")
    comp_col1, comp_col2 = st.columns(2)

    with comp_col1:
        s_color = "#00ff00" if swing_state['realized_pnl'] >= 20.0 else "#ff4b4b"
        st.markdown(
            f"<div style='padding:12px; border-radius:10px; background-color:#1e2129; border-left: 5px solid #3498db;'>"
            f"<b>🐢 Swing ({swing_leverage}x | ${swing_margin:.0f}/trade)</b><br>"
            f"<span style='font-size:24px; color:{s_color}; font-weight:bold;'>${swing_state['realized_pnl']:.2f}</span><br>"
            f"<small>Active: {s_act} | Closed: {s_tot} | Win Rate: <b>{s_wr:.1f}%</b></small>"
            f"</div>",
            unsafe_allow_html=True
        )

    with comp_col2:
        sc_color = "#00ff00" if scalp_state['realized_pnl'] >= 20.0 else "#ff4b4b"
        st.markdown(
            f"<div style='padding:12px; border-radius:10px; background-color:#1e2129; border-left: 5px solid #f39c12;'>"
            f"<b>⚡ Pro Scalping ({scalp_leverage}x | ${scalp_margin:.0f}/trade)</b><br>"
            f"<span style='font-size:24px; color:{sc_color}; font-weight:bold;'>${scalp_state['realized_pnl']:.2f}</span><br>"
            f"<small>Active: {sc_act} | Closed: {sc_tot} | Win Rate: <b>{sc_wr:.1f}%</b></small>"
            f"</div>",
            unsafe_allow_html=True
        )

    st.markdown("---")

    tab_swing, tab_scalp = st.tabs([f"🐢 Swing ({s_act} Active)", f"⚡ Pro Scalping ({sc_act} Active)"])

    with tab_swing:
        render_strategy_tab("swing", swing_state, live_prices, swing_radar, SWING_CONFIG['cooldown_mins'], swing_margin, swing_leverage)

    with tab_scalp:
        render_strategy_tab("scalping", scalp_state, live_prices, scalp_radar, SCALP_CONFIG['cooldown_mins'], scalp_margin, scalp_leverage)

live_dashboard()
