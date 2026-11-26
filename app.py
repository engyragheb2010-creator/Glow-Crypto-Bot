import streamlit as st
import ccxt
import pandas as pd
import pandas_ta as ta
import requests
import time
import json
import os
from datetime import datetime, timezone, timedelta

try:
    from zoneinfo import ZoneInfo
    CAIRO_TZ = ZoneInfo("Africa/Cairo")
except Exception:
    CAIRO_TZ = timezone(timedelta(hours=2))

def now_cairo():
    return datetime.now(CAIRO_TZ)

# ==========================================
# 1. إعدادات الشاشة والربط السحابي (JSONBin)
# ==========================================
st.set_page_config(page_title="SMC Sniper Bot - Classic Swing (5x)", layout="wide")
st.title("🤖 SMC Sniper Bot — 🐢 Classic Swing (Futures 5x)")

# مفاتيح الربط السحابي الخاصة بك
JSONBIN_BIN_ID = "6b02bc93ffd5d16053d55d5d"
JSONBIN_API_KEY = "$2a$10$Y2gG93ZSPm0TetpeSZzUJOjJejPRL42P17olP0s3edOSXMlmWCkFi"

# ==========================================
# 2. إعدادات العملات والعمولة والذاكرة السحابية
# ==========================================
SYMBOLS = ['SUI/USDT', 'SOL/USDT', 'AVAX/USDT', 'NEAR/USDT', 'BNB/USDT', 'XRP/USDT']
SYMBOL_PRIORITY = {
    'SUI/USDT': 6,
    'SOL/USDT': 5,
    'AVAX/USDT': 4,
    'NEAR/USDT': 3,
    'BNB/USDT': 2,
    'XRP/USDT': 1
}
MAX_ACTIVE_TRADES = 4
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
        'swing': get_default_strategy_state(20.0)
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
    if 'swing' in raw_data and isinstance(raw_data['swing'], dict):
        for field, val in get_default_strategy_state().items():
            if field not in raw_data['swing']:
                raw_data['swing'][field] = val
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
            res = requests.get(url, headers=headers, timeout=15)
            if res.status_code == 200:
                return normalize_data(res.json().get("record", {}))
        except Exception as e:
            st.warning(f"Cloud load warning: {e}")

    if os.path.exists(DATA_FILE):
        try:
            with open(DATA_FILE, 'r', encoding='utf-8') as f:
                return normalize_data(json.load(f))
        except Exception:
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
            requests.put(url, json=data, headers=headers, timeout=15)
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
# 4. دوال جلب البيانات والمؤشرات والإحصائيات
# ==========================================
@st.cache_data(ttl=120)
def fetch_data_slow(symbol, timeframe, limit=250):
    try:
        bars = exchange.fetch_ohlcv(symbol, timeframe, limit=limit)
        df = pd.DataFrame(bars, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
        for col in ['open', 'high', 'low', 'close', 'volume']:
            df[col] = pd.to_numeric(df[col], errors='coerce')

        atr_s = ta.atr(df['high'], df['low'], df['close'], length=14)
        df['ATR'] = atr_s if atr_s is not None and not atr_s.empty else 0.0

        ema50_s = ta.ema(df['close'], length=50)
        df['EMA50'] = ema50_s if ema50_s is not None and not ema50_s.empty else df['close']

        ema200_s = ta.ema(df['close'], length=200)
        df['EMA200'] = ema200_s if ema200_s is not None and not ema200_s.empty else df['close']

        rsi_s = ta.rsi(df['close'], length=14)
        df['RSI'] = rsi_s if rsi_s is not None and not rsi_s.empty else 50.0

        adx_df = ta.adx(df['high'], df['low'], df['close'], length=14)
        df['ADX'] = adx_df['ADX_14'] if (adx_df is not None and 'ADX_14' in adx_df.columns) else 0.0

        return df
    except Exception:
        return None

def check_auto_adx(adx_curr, adx_prev, adx_strong=18.0, adx_rising_min=14.0):
    return (adx_curr > adx_strong) or (adx_curr > adx_rising_min and adx_curr > adx_prev)

def analyze_smc(df, adx_strong=18.0, adx_rising_min=14.0, rsi_buy=(50, 68), rsi_sell=(32, 50)):
    if df is None or len(df) < 200:
        return 'NONE', 0.0, 0.0

    closed_candle = df['close'].iloc[-2]
    prev_high = df['high'].iloc[-3]
    prev_low = df['low'].iloc[-3]

    raw_atr = df['ATR'].iloc[-2]
    atr_val = float(raw_atr) if (raw_atr is not None and not pd.isna(raw_atr)) else 0.0

    ema_50 = df['EMA50'].iloc[-2]
    ema_200 = df['EMA200'].iloc[-2]
    rsi = df['RSI'].iloc[-2]

    raw_adx = df['ADX'].iloc[-2]
    prev_adx = df['ADX'].iloc[-3]
    adx = float(raw_adx) if (raw_adx is not None and not pd.isna(raw_adx)) else 0.0
    adx_p = float(prev_adx) if (prev_adx is not None and not pd.isna(prev_adx)) else 0.0

    if not check_auto_adx(adx, adx_p, adx_strong, adx_rising_min):
        return 'NONE', 0.0, adx

    if ema_50 > ema_200 and closed_candle > ema_50 and closed_candle > prev_high and rsi_buy[0] < rsi < rsi_buy[1]:
        return 'BUY', atr_val, adx
    elif ema_50 < ema_200 and closed_candle < ema_50 and closed_candle < prev_low and rsi_sell[0] < rsi < rsi_sell[1]:
        return 'SELL', atr_val, adx

    return 'NONE', 0.0, adx

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

def build_coin_stats(state):
    stats = {}
    for ct in state.get('closed_trades', []):
        sym = ct.get('symbol')
        pnl = float(ct.get('net_pnl_usd', 0.0))
        if not sym:
            continue
        if sym not in stats:
            stats[sym] = {'trades': 0, 'wins': 0, 'losses': 0, 'net_usd': 0.0}
        stats[sym]['trades'] += 1
        stats[sym]['net_usd'] += pnl
        if pnl > 0:
            stats[sym]['wins'] += 1
        else:
            stats[sym]['losses'] += 1

    for sym, tr in state.get('active_trades', {}).items():
        if tr.get('trade_closed', False):
            pnl = float(tr.get('fixed_net_usd', 0.0))
            if sym not in stats:
                stats[sym] = {'trades': 0, 'wins': 0, 'losses': 0, 'net_usd': 0.0}
            stats[sym]['trades'] += 1
            stats[sym]['net_usd'] += pnl
            if pnl > 0:
                stats[sym]['wins'] += 1
            else:
                stats[sym]['losses'] += 1

    rows = []
    sorted_coins = sorted(stats.items(), key=lambda x: (x[1]['net_usd'], x[1]['wins']), reverse=True)
    for idx, (sym, d) in enumerate(sorted_coins):
        wr = (d['wins'] / d['trades'] * 100) if d['trades'] > 0 else 0.0
        if d['net_usd'] > 0 and idx < 4:
            badge = "🏆 Top Pick"
        elif d['net_usd'] > 0:
            badge = "✅ Profitable"
        elif d['net_usd'] == 0:
            badge = "➖ Breakeven"
        else:
            badge = "⚠️ Losing"

        rows.append({
            "🪙 Coin": sym,
            "💰 Net PnL": f"${d['net_usd']:+.2f}",
            "Status": badge,
            "✅ W/L": f"{d['wins']}W / {d['losses']}L",
            "🎯 Win%": f"{wr:.0f}%"
        })
    return rows

# ==========================================
# 5. الشريط الجانبي (إعدادات Classic Swing 5x)
# ==========================================
st.sidebar.markdown("### ⚙️ Classic Swing Settings")
if is_cloud_configured():
    st.sidebar.success("☁️ Cloud Memory: Connected")
else:
    st.sidebar.warning("⚠️ Cloud Memory: Not Connected")

st.sidebar.caption(f"🤖 1H EMA Alignment + Best-Signal (Max {MAX_ACTIVE_TRADES} Trades)")
st.sidebar.caption("💸 OKX Futures Fee: 0.10% (0.05% In + 0.05% Out)")

swing_margin = st.sidebar.number_input("Margin / Trade ($):", min_value=1.0, value=5.0, step=0.5)
swing_leverage = st.sidebar.slider("Leverage (x):", min_value=1, max_value=20, value=5)
st.sidebar.caption(f"Position Size: **${swing_margin * swing_leverage:.2f}** | Est. Fee: **${swing_margin * swing_leverage * OKX_ROUND_TRIP_FEE:.3f}**")

st.sidebar.markdown("---")
new_cap = st.sidebar.number_input("Starting Capital ($):", min_value=1.0, value=20.0, step=1.0)

if st.sidebar.button("🔄 Reset Classic Swing"):
    st.session_state.bot_data['swing'] = get_default_strategy_state(new_cap)
    save_data()
    st.sidebar.success("Classic Swing portfolio reset!")
    st.rerun()

# ==========================================
# 6. محرك التحديث والرادار (مع فلتر اتجاه الساعة)
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

        # TP1 (إغلاق 50% من الصفقة وخصم عمولة النصف ده + نقل الاستوب للدخول)
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
            trade['close_time_str'] = now_cairo().strftime('%Y-%m-%d %I:%M:%S %p')

            if tp2_reached and not sl_hit:
                trade['fixed_close_price'] = trade['tp2']
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
                trade['fixed_close_price'] = trade['sl']
                if trade.get('tp1_hit', False):
                    half_fee = (pos_size * 0.5) * OKX_ROUND_TRIP_FEE
                    state['realized_pnl'] -= half_fee
                    total_net_usd = trade.get('tp1_realized_usd', 0.0) - half_fee
                    trade['close_reason'] = "🛡️ Breakeven SL (TP1 Secured)"
                else:
                    if side == 'BUY':
                        sl_pnl_pct = ((trade['sl'] - trade['entry']) / trade['entry']) * 100.0
                    else:
                        sl_pnl_pct = ((trade['entry'] - trade['sl']) / trade['entry']) * 100.0
                    gross_usd = pos_size * (sl_pnl_pct / 100.0)
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

def scan_swing_mode(state, config, dfs_cache, margin, leverage):
    radar_rows = []
    candidates = []
    now_epoch = time.time()
    changed = False

    htf, ltf = config['htf'], config['ltf']
    adx_strong = config['adx_strong']
    adx_rising_min = config['adx_rising_min']
    rsi_buy, rsi_sell = config['rsi_buy'], config['rsi_sell']
    open_count = sum(1 for t in state['active_trades'].values() if not t.get('trade_closed', False))

    for sym in SYMBOLS:
        df_htf = dfs_cache.get((sym, htf))
        df_ltf = dfs_cache.get((sym, ltf))
        if df_htf is None or df_ltf is None:
            continue

        current_price = df_ltf['close'].iloc[-1]
        sig_htf, _, adx_htf = analyze_smc(df_htf, adx_strong=adx_strong, adx_rising_min=adx_rising_min, rsi_buy=rsi_buy, rsi_sell=rsi_sell)
        sig_ltf, _, _ = analyze_smc(df_ltf, adx_strong=adx_strong, adx_rising_min=adx_rising_min, rsi_buy=rsi_buy, rsi_sell=rsi_sell)
        vol_ltf = df_ltf['volume'].iloc[-1]

        raw_atr = df_ltf['ATR'].iloc[-2]
        atr_val = float(raw_atr) if (raw_atr is not None and not pd.isna(raw_atr)) else 0.0

        raw_adx = df_ltf['ADX'].iloc[-2]
        prev_adx = df_ltf['ADX'].iloc[-3]
        adx_val = float(raw_adx) if (raw_adx is not None and not pd.isna(raw_adx)) else 0.0
        adx_prev_val = float(prev_adx) if (prev_adx is not None and not pd.isna(prev_adx)) else 0.0
        adx_dir = "↗️" if adx_val > adx_prev_val else "↘️"

        raw_rsi = df_ltf['RSI'].iloc[-2]
        rsi_val = float(raw_rsi) if (raw_rsi is not None and not pd.isna(raw_rsi)) else 50.0

        # تأكيد ترتيب متوسطات فريم الساعة (EMA50 مع EMA200) لمنع الدخول في ارتدادات وهمية
        htf_close = df_htf['close'].iloc[-2]
        htf_ema50 = df_htf['EMA50'].iloc[-2]
        htf_ema200 = df_htf['EMA200'].iloc[-2]
        trend_htf_up = (htf_ema50 > htf_ema200) and (htf_close > htf_ema50)
        trend_htf_down = (htf_ema50 < htf_ema200) and (htf_close < htf_ema50)

        ema50 = df_ltf['EMA50'].iloc[-2]
        ema200 = df_ltf['EMA200'].iloc[-2]
        closed_ltf = df_ltf['close'].iloc[-2]
        prev_high = df_ltf['high'].iloc[-3]
        prev_low = df_ltf['low'].iloc[-3]

        if sym in state['active_trades']:
            t_obj = state['active_trades'][sym]
            if t_obj.get('trade_closed', False):
                rem = int((state['cooldowns'].get(sym, 0) - now_epoch) // 60)
                status = f"🛌 Resting ({rem}m left)" if rem > 0 else "🔒 Closed (Ready to Archive)"
            else:
                status = "🟢 Active Trade"
        elif sym in state['cooldowns'] and now_epoch < state['cooldowns'][sym]:
            rem = int((state['cooldowns'][sym] - now_epoch) // 60)
            status = f"🛌 Resting ({rem}m left)"
        elif open_count >= MAX_ACTIVE_TRADES:
            status = f"⏸️ Max Trades ({open_count}/{MAX_ACTIVE_TRADES})"
        elif not check_auto_adx(adx_val, adx_prev_val, adx_strong, adx_rising_min):
            status = f"😴 Flat Market (ADX {adx_val:.1f} {adx_dir})"
        else:
            if trend_htf_up:
                if ema50 <= ema200: status = f"⏳ Wait {ltf} EMA50>200 ({htf} Up)"
                elif not (rsi_buy[0] < rsi_val < rsi_buy[1]): status = f"⏳ Wait RSI {rsi_buy[0]}-{rsi_buy[1]}"
                elif closed_ltf <= ema50: status = "⏳ Wait Close>EMA50"
                elif closed_ltf <= prev_high: status = "⏳ Wait High Breakout"
                else: status = "👀 Ready (BUY)"
            elif trend_htf_down:
                if ema50 >= ema200: status = f"⏳ Wait {ltf} EMA50<200 ({htf} Down)"
                elif not (rsi_sell[0] < rsi_val < rsi_sell[1]): status = f"⏳ Wait RSI {rsi_sell[0]}-{rsi_sell[1]}"
                elif closed_ltf >= ema50: status = "⏳ Wait Close<EMA50"
                elif closed_ltf >= prev_low: status = "⏳ Wait Low Breakout"
                else: status = "👀 Ready (SELL)"
            else:
                status = f"🔄 {htf} Trend Transition (Wait EMA50/200)"

        radar_rows.append({
            "🪙 Symbol": sym,
            "💵 Price": f"${current_price:.4f}",
            f"💪 {ltf} ADX": f"{adx_val:.1f} {adx_dir}",
            f"📈 {ltf} RSI": f"{rsi_val:.1f}",
            "📊 Volume": f"{vol_ltf:.1f}",
            "Status": status
        })

        # تخطي العملة لو مشغولة أو في فترة راحة أو وصلنا للحد الأقصى (4 صفقات)
        if sym in state['active_trades'] or open_count >= MAX_ACTIVE_TRADES:
            continue
        if sym in state['cooldowns'] and now_epoch < state['cooldowns'][sym]:
            continue

        eff_atr = atr_val if atr_val > 0 else (current_price * 0.01)
        entry_side, mode_label, tf_priority, sig_adx = None, None, 0, 0.0
        tp1_mult, tp2_mult, sl_mult, min_tp = config['tp1_mult'], config['tp2_mult'], config['sl_mult'], config['min_tp']

        if sig_htf in ['BUY', 'SELL']:
            entry_side = sig_htf
            mode_label = config['htf_label']
            tf_priority = 2
            sig_adx = adx_htf
            raw_htf_atr = df_htf['ATR'].iloc[-2]
            eff_atr = float(raw_htf_atr) if (raw_htf_atr is not None and not pd.isna(raw_htf_atr) and raw_htf_atr > 0) else (current_price * 0.015)
            tp1_mult, tp2_mult, sl_mult, min_tp = config['htf_tp1'], config['htf_tp2'], config['htf_sl'], config['htf_min_tp']
        elif (sig_ltf == 'BUY' and trend_htf_up) or (sig_ltf == 'SELL' and trend_htf_down):
            entry_side = sig_ltf
            mode_label = config['ltf_label']
            tf_priority = 1
            sig_adx = adx_val

        if entry_side:
            if entry_side == 'BUY':
                tp1 = current_price + max(eff_atr * tp1_mult, current_price * min_tp)
                tp2 = current_price + max(eff_atr * tp2_mult, current_price * (min_tp * 2))
                sl = current_price - max(eff_atr * sl_mult, current_price * (min_tp * 0.9))
            else:
                tp1 = current_price - max(eff_atr * tp1_mult, current_price * min_tp)
                tp2 = current_price - max(eff_atr * tp2_mult, current_price * (min_tp * 2))
                sl = current_price + max(eff_atr * sl_mult, current_price * (min_tp * 0.9))

            candidates.append({
                'sym': sym,
                'entry': current_price,
                'tp1': tp1,
                'tp2': tp2,
                'sl': sl,
                'mode': mode_label,
                'side': entry_side,
                'rank_score': (tf_priority, sig_adx, SYMBOL_PRIORITY.get(sym, 0))
            })

    # ملء الأماكن المتاحة بأقوى الإشارات بالترتيب حتى الحد الأقصى (4 صفقات)
    slots_available = MAX_ACTIVE_TRADES - open_count
    if candidates and slots_available > 0:
        candidates.sort(key=lambda x: x['rank_score'], reverse=True)
        for best in candidates[:slots_available]:
            now_str = now_cairo().strftime('%Y-%m-%d %I:%M:%S %p')
            state['active_trades'][best['sym']] = {
                'entry': best['entry'],
                'tp1': best['tp1'],
                'tp2': best['tp2'],
                'sl': best['sl'],
                'original_sl': best['sl'],
                'mode': best['mode'],
                'side': best['side'],
                'open_time': now_str,
                'open_timestamp': time.time(),
                'tp1_hit': False,
                'tp2_hit': False,
                'trade_closed': False,
                'margin': margin,
                'leverage': leverage
            }
            changed = True

    return radar_rows, changed

def render_strategy_section(state, live_prices, radar_rows, cooldown_mins, default_margin, default_lev):
    st.markdown(f"### 🟢 Active Trades (Max: {MAX_ACTIVE_TRADES})")
    if not state['active_trades']:
        st.info("No active trades right now. Scanning market for confirmed signals...")

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
            - **🕒 Opened (Cairo):** {trade.get('open_time', 'N/A')} | **⏳ Duration:** {duration_str}
            - **🎯 TP1 (50%):** ${trade['tp1']:.4f} {tp1_tag}
            - **🚀 TP2 (50%):** ${trade['tp2']:.4f} {tp2_tag}
            - <span style='color:#ff4b4b'>**🛑 SL:** ${trade['sl']:.4f}</span>
            """, unsafe_allow_html=True)

            if st.button(f"Move {sym} to Archive", key=f"rem_act_swing_{sym}"):
                close_time_str = trade.get('close_time_str', now_cairo().strftime('%Y-%m-%d %I:%M:%S %p'))
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
                if st.button("Delete Record", key=f"rem_cls_swing_{orig_idx}"):
                    state['closed_trades'].pop(orig_idx)
                    save_data()
                    st.rerun()

    st.markdown("---")
    st.markdown("### 📡 Live Market Radar")
    st.dataframe(radar_rows, use_container_width=True)

# ==========================================
# 7. لوحة التحكم الحية (تحديث تلقائي كل 15 ثانية بتوقيت مصر)
# ==========================================
CLASSIC_SWING_CONFIG = {
    'htf': '1h', 'ltf': '15m',
    'adx_strong': 18.0, 'adx_rising_min': 14.0,
    'rsi_buy': (50, 68), 'rsi_sell': (32, 50),
    'tp1_mult': 1.8, 'tp2_mult': 3.5, 'sl_mult': 1.8, 'min_tp': 0.015,
    'htf_tp1': 2.0, 'htf_tp2': 4.0, 'htf_sl': 2.0, 'htf_min_tp': 0.02,
    'htf_label': "🎯 Pro Swing (1h)", 'ltf_label': "🐢 Classic Swing (15m)",
    'cooldown_mins': 60
}

@st.fragment(run_every=15)
def live_dashboard():
    col1, col2 = st.columns([1, 2])
    with col1:
        if st.button("🔄 Force Update Now"):
            st.rerun()
    with col2:
        st.caption(f"🕒 Cairo Time: {now_cairo().strftime('%I:%M:%S %p')} (Auto-refreshes every 15s)")

    classic_state = st.session_state.bot_data['swing']

    needed_tickers = set(classic_state['active_trades'].keys())
    live_prices = {}
    for sym in needed_tickers:
        try:
            live_prices[sym] = exchange.fetch_ticker(sym)['last']
        except Exception:
            pass

    dfs_cache = {}
    for sym in SYMBOLS:
        dfs_cache[(sym, '1h')] = fetch_data_slow(sym, '1h')
        dfs_cache[(sym, '15m')] = fetch_data_slow(sym, '15m')

    c1 = update_active_trades(classic_state, live_prices, CLASSIC_SWING_CONFIG['cooldown_mins'], swing_margin, swing_leverage)
    classic_radar, c2 = scan_swing_mode(classic_state, CLASSIC_SWING_CONFIG, dfs_cache, swing_margin, swing_leverage)

    if c1 or c2:
        save_data()

    s_tot, s_win, s_wr, s_act = calc_stats(classic_state)
    bal = classic_state['realized_pnl']
    s_color = "#00ff00" if bal >= 20.0 else "#ff4b4b"

    st.markdown(
        f"<div style='padding:16px; margin-bottom:12px; border-radius:10px; background-color:#1e2129; color:#ffffff; border-left: 5px solid #3498db;'>"
        f"<b style='color:#ffffff; font-size:16px;'>🐢 Classic Swing Portfolio ({swing_leverage}x | ${swing_margin:.2f}/trade — Max {MAX_ACTIVE_TRADES} Trades)</b><br>"
        f"<span style='font-size:28px; color:{s_color}; font-weight:bold;'>${bal:.2f}</span><br>"
        f"<span style='color:#e2e8f0; font-size:14px;'>Active: <b>{s_act}/{MAX_ACTIVE_TRADES}</b> | Closed: <b>{s_tot}</b> | Win Rate: <b style='color:#ffffff;'>{s_wr:.1f}%</b></span>"
        f"</div>",
        unsafe_allow_html=True
    )

    st.markdown("### 🏆 Classic Swing Top Picks")
    classic_coins = build_coin_stats(classic_state)
    if classic_coins:
        st.dataframe(classic_coins, use_container_width=True, hide_index=True)
    else:
        st.info("No closed trades in Classic Swing yet.")

    st.markdown("---")
    render_strategy_section(classic_state, live_prices, classic_radar, CLASSIC_SWING_CONFIG['cooldown_mins'], swing_margin, swing_leverage)

live_dashboard()
