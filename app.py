import streamlit as st
import ccxt
import numpy as np
import pandas as pd
import time
import json
import os

st.set_page_config(page_title="Glow Pro Smart Money Bot", page_icon="🐋", layout="wide")
st.title("🐋 تطبيق التداول المؤسسي (SMC & Squeeze Momentum)")

API_KEY = "41e8e6d1-3d2d-4861-b0df-61ccdb79e34b"
SECRET_KEY = "1FC2FDF62E1F188458144B7700759BC3" 
PASSPHRASE = 'Ahmedengy2010@'

# --- English Status Labels ---
PENDING = '⏳ Pending'
ACTIVE = '🟢 Active'
SECURED = '🎯 Secured (TP1 Hit)'
CLOSED_TP2 = '🏆 Closed (Hit TP2)'
CLOSED_SL = '🛑 Closed (Hit SL)'
CLOSED_BE = '🛡️ Closed (Breakeven)'
CLOSED_MANUAL = '⏹️ Closed (Manual)'

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
if 'trend_opps' not in st.session_state: st.session_state.trend_opps = []
if 'tracked_trades' not in st.session_state: st.session_state.tracked_trades = load_portfolio()

def get_mark_price(exch, sym):
    try:
        ticker = exch.fetch_ticker(sym)
        mark = ticker.get('mark')
        if mark is None:
            mark = ticker.get('info', {}).get('markPx')
        return float(mark) if mark is not None else ticker['last']
    except:
        return 0

def calculate_atr(highs, lows, closes, period=14):
    tr_list = [highs[0] - lows[0]]
    for i in range(1, len(closes)):
        h_l = highs[i] - lows[i]
        h_pc = abs(highs[i] - closes[i-1])
        l_pc = abs(lows[i] - closes[i-1])
        tr_list.append(max(h_l, h_pc, l_pc))
    atr = pd.Series(tr_list).rolling(window=period).mean().iloc[-1]
    return atr if not np.isnan(atr) else (highs[-1] * 0.01)

# فلتر الاتجاه العام الصارم لمنع التداول عكس السوق في السكالبينج (EMA 50 vs EMA 200)
def is_trend_favorable(sym, direction):
    try:
        # سحب 250 شمعة لفريم الساعة عشان نقدر نحسب متوسط 200 بدقة
        ohlcv_1h = exchange.fetch_ohlcv(sym, '1h', limit=250)
        df_1h = pd.DataFrame(ohlcv_1h, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
        
        # حساب Exponential Moving Average (EMA)
        df_1h['ema50'] = df_1h['close'].ewm(span=50, adjust=False).mean()
        df_1h['ema200'] = df_1h['close'].ewm(span=200, adjust=False).mean()
        
        ema50_current = df_1h['ema50'].iloc[-1]
        ema200_current = df_1h['ema200'].iloc[-1]
        
        # التقييم الصارم
        is_uptrend = ema50_current > ema200_current
        
        if direction == "LONG" and not is_uptrend:
            return False # التريند العام هابط، لا تدخل شراء
        if direction == "SHORT" and is_uptrend:
            return False # التريند العام صاعد، لا تدخل بيع
            
        return True
    except Exception as e:
        return True

def detect_fvg_entry(highs, lows, closes, curr_price):
    for i in range(len(closes)-2, len(closes)-10, -1):
        if lows[i] > highs[i-2]:
            fvg_top = lows[i]
            fvg_bottom = highs[i-2]
            if fvg_bottom <= curr_price <= fvg_top:
                return "LONG", fvg_bottom
        elif highs[i] < lows[i-2]:
            fvg_bottom = highs[i]
            fvg_top = lows[i-2]
            if fvg_bottom <= curr_price <= fvg_top:
                return "SHORT", fvg_top
    return None, 0

def calculate_squeeze(highs, lows, closes, period=20, bb_mult=2.0, kc_mult=1.5):
    df = pd.DataFrame({'high': highs, 'low': lows, 'close': closes})
    df['sma'] = df['close'].rolling(period).mean()
    df['std'] = df['close'].rolling(period).std()
    
    df['bb_upper'] = df['sma'] + bb_mult * df['std']
    df['bb_lower'] = df['sma'] - bb_mult * df['std']
    
    df['tr'] = np.maximum(df['high'] - df['low'], np.maximum(abs(df['high'] - df['close'].shift(1)), abs(df['low'] - df['close'].shift(1))))
    df['atr'] = df['tr'].rolling(period).mean()
    df['kc_upper'] = df['sma'] + kc_mult * df['atr']
    df['kc_lower'] = df['sma'] - kc_mult * df['atr']
    
    df['squeeze_on'] = (df['bb_lower'] > df['kc_lower']) & (df['bb_upper'] < df['kc_upper'])
    df['squeeze_off'] = (df['bb_lower'] < df['kc_lower']) | (df['bb_upper'] > df['kc_upper'])
    df['mom'] = df['close'] - df['sma'] 
    
    is_sq_off = df['squeeze_off'].iloc[-1]
    was_sq_on = df['squeeze_on'].iloc[-2] or df['squeeze_on'].iloc[-3] 
    momentum = df['mom'].iloc[-1]
    
    return is_sq_off, was_sq_on, momentum

def play_audio_alert():
    audio_html = """
        <audio autoplay>
          <source src="https://assets.mixkit.co/active_storage/sfx/2869/2869-preview.mp3" type="audio/mp3">
        </audio>
    """
    st.markdown(audio_html, unsafe_allow_html=True)

def get_decimals(price):
    if price < 1: return 4
    elif price < 10: return 3
    else: return 2

def track_trade(opp, trade_type):
    for t in st.session_state.tracked_trades:
        if t['symbol'] == opp['symbol'] and t['status'] in [PENDING, ACTIVE, SECURED]:
            st.toast(f"Trade already exists!")
            return
    new_trade = {
        'id': f"{opp['symbol']}_{time.time()}", 'symbol': opp['symbol'], 'type': trade_type,
        'direction': opp.get('direction', '🟢 LONG'), 'entry': opp['buy'], 
        'tp1': opp['tp1'], 'tp2': opp['tp2'], 'sl': opp['sl'], 
        'status': PENDING, 'secured': False, 'pnl_pct': 0.0
    }
    st.session_state.tracked_trades.append(new_trade)
    save_portfolio(st.session_state.tracked_trades)
    st.toast(f"Added to portfolio!")

def cancel_trade_action(trade_id):
    st.session_state.tracked_trades = [t for t in st.session_state.tracked_trades if t['id'] != trade_id]
    save_portfolio(st.session_state.tracked_trades)

def close_trade_action(trade_id, symbol, direction, entry_val):
    curr_price = get_mark_price(exchange, symbol)
    for t in st.session_state.tracked_trades:
        if t['id'] == trade_id:
            t['status'] = CLOSED_MANUAL
            is_long = 'LONG' in direction
            pnl = ((curr_price - entry_val) / entry_val) * 100 if is_long else ((entry_val - curr_price) / entry_val) * 100
            t['pnl_pct'] = round(pnl, 2)
            break
    save_portfolio(st.session_state.tracked_trades)

active_or_failed_symbols = [
    t['symbol'] for t in st.session_state.tracked_trades 
    if t['status'] in [PENDING, ACTIVE, SECURED] or 'Closed' in t['status']
]

col1, col2 = st.columns([3, 1])
with col1:
    st.success("🐋 البوت يعمل الآن بمنطق الأموال الذكية (SMC) والانفجارات السعرية.")
    
    # 1. تصفية العملات لتشمل الأقوى فقط (بدون DOGE)
    symbols = ['BTC/USDT', 'ETH/USDT', 'BNB/USDT', 'SOL/USDT']
    
    scalp_opps = []
    trend_opps = []
    
    for symbol in symbols:
        try:
            curr_price = get_mark_price(exchange, symbol)
            if curr_price == 0: continue
            dec = get_decimals(curr_price)
            
            # فحص السكالبينج (SMC FVG)
            ohlcv_5m = exchange.fetch_ohlcv(symbol, '5m', limit=100)
            h5 = np.array([c[2] for c in ohlcv_5m])
            l5 = np.array([c[3] for c in ohlcv_5m])
            c5 = np.array([c[4] for c in ohlcv_5m])
            curr = c5[-1]
            atr_5 = calculate_atr(h5, l5, c5, 14)
            
            if symbol not in active_or_failed_symbols:
                fvg_dir, fvg_sl_level = detect_fvg_entry(h5, l5, c5, curr)
                
                if fvg_dir:
                    # تفعيل فلتر الاتجاه الصارم للسكالبينج
                    if is_trend_favorable(symbol, fvg_dir):
                        if fvg_dir == "LONG":
                            scalp_opps.append({
                                'symbol': symbol, 'direction': '🟢 LONG (SMC FVG)', 'price': curr, 'score': 95,
                                'buy': round(curr, dec), 'tp1': round(curr * 1.006, dec), 'tp2': round(curr * 1.015, dec), 
                                'sl': round(min(curr - (1.0 * atr_5), fvg_sl_level * 0.998), dec)
                            })
                        elif fvg_dir == "SHORT":
                            scalp_opps.append({
                                'symbol': symbol, 'direction': '🔴 SHORT (SMC FVG)', 'price': curr, 'score': 95,
                                'buy': round(curr, dec), 'tp1': round(curr * 0.994, dec), 'tp2': round(curr * 0.985, dec), 
                                'sl': round(max(curr + (1.0 * atr_5), fvg_sl_level * 1.002), dec)
                            })
                
            # فحص التريند (Squeeze Breakout)
            if symbol not in active_or_failed_symbols:
                ohlcv_15m = exchange.fetch_ohlcv(symbol, '15m', limit=100)
                h15 = np.array([c[2] for c in ohlcv_15m])
                l15 = np.array([c[3] for c in ohlcv_15m])
                c15 = np.array([c[4] for c in ohlcv_15m])
                curr_15 = c15[-1]
                atr_15 = calculate_atr(h15, l15, c15, 14)
                
                is_sq_off, was_sq_on, mom = calculate_squeeze(h15, l15, c15)
                
                if is_sq_off and was_sq_on:
                    if mom > 0:
                        trend_opps.append({
                            'symbol': symbol, 'direction': '🚀 LONG (Squeeze Breakout)', 'price': curr_15, 'score': 98,
                            'buy': round(curr_15, dec), 'tp1': round(curr_15 * 1.015, dec), 'tp2': round(curr_15 * 1.032, dec), 'sl': round(curr_15 - (1.5 * atr_15), dec)
                        })
                    elif mom < 0:
                        trend_opps.append({
                            'symbol': symbol, 'direction': '💥 SHORT (Squeeze Breakout)', 'price': curr_15, 'score': 98,
                            'buy': round(curr_15, dec), 'tp1': round(curr_15 * 0.985, dec), 'tp2': round(curr_15 * 0.968, dec), 'sl': round(curr_15 + (1.5 * atr_15), dec)
                        })
        except Exception as e: 
            continue
            
    # لوجيك التنبيهات المحدث
    new_opportunities_found = False
    
    # مقارنة الفرص الحالية بالفرص في الجلسة السابقة
    current_opp_symbols = [opp['symbol'] for opp in scalp_opps + trend_opps]
    previous_opp_symbols = [opp['symbol'] for opp in st.session_state.scalping_opps + st.session_state.trend_opps]
    
    for sym in current_opp_symbols:
        if sym not in previous_opp_symbols:
            new_opportunities_found = True
            st.toast(f"🔔 فرصة جديدة تم رصدها على {sym}!", icon="🎯")
            
    if new_opportunities_found:
        play_audio_alert()
        
    st.session_state.scalping_opps = scalp_opps
    st.session_state.trend_opps = trend_opps

with col2:
    if st.button('🔄 Update / Check PnL'):
        with st.spinner('Checking Mark Prices...'):
            report_logs = []
            for t in st.session_state.tracked_trades:
                if t['status'] in [PENDING, ACTIVE, SECURED]:
                    try:
                        curr = get_mark_price(exchange, t['symbol'])
                        is_long = 'LONG' in t['direction']
                        entry_val = t['entry']
                        
                        if t['status'] == PENDING:
                            if (is_long and curr <= entry_val) or (not is_long and curr >= entry_val): 
                                t['status'] = ACTIVE
                        
                        if t['status'] != PENDING:
                            if is_long:
                                pnl = ((curr - entry_val) / entry_val) * 100
                            else:
                                pnl = ((entry_val - curr) / entry_val) * 100
                            t['pnl_pct'] = round(pnl, 2)
                            pnl_label = f"PnL: +{t['pnl_pct']}%" if t['pnl_pct'] >= 0 else f"PnL: {t['pnl_pct']}%"
                            report_logs.append(f"{t['symbol']} | Price: {curr} | {pnl_label}")
                        else:
                            t['pnl_pct'] = 0.0
                            report_logs.append(f"{t['symbol']} | Price: {curr} | ⏳ Pending")
                        
                        tp1 = t.get('tp1', t.get('tp', 0))
                        tp2 = t.get('tp2', t.get('tp', 0))
                        
                        if t['status'] in [ACTIVE, SECURED]:
                            if is_long:
                                if curr >= tp1 and t['status'] == ACTIVE:
                                    t['status'] = SECURED
                                    t['sl'] = entry_val
                                    t['secured'] = True
                                elif curr >= tp2: 
                                    t['status'] = CLOSED_TP2
                                elif curr <= t['sl']: 
                                    t['status'] = CLOSED_SL if not t.get('secured', False) else CLOSED_BE
                            else:
                                if curr <= tp1 and t['status'] == ACTIVE:
                                    t['status'] = SECURED
                                    t['sl'] = entry_val
                                    t['secured'] = True
                                elif curr <= tp2: 
                                    t['status'] = CLOSED_TP2
                                elif curr >= t['sl']: 
                                    t['status'] = CLOSED_SL if not t.get('secured', False) else CLOSED_BE
                    except: pass
            save_portfolio(st.session_state.tracked_trades)
            st.session_state.report_logs = report_logs
        st.success("Updated successfully!")
        
    if 'report_logs' in st.session_state and st.session_state.report_logs:
        with st.expander("📊 Live PnL Report", expanded=True):
            for log in st.session_state.report_logs:
                if "+" in log:
                    st.markdown(f"<p style='color:green; font-weight:bold;'>{log}</p>", unsafe_allow_html=True)
                elif "Pending" in log:
                    st.markdown(f"<p style='color:gray; font-weight:bold;'>{log}</p>", unsafe_allow_html=True)
                else:
                    st.markdown(f"<p style='color:red; font-weight:bold;'>{log}</p>", unsafe_allow_html=True)
        
    st.markdown("---")
    if st.button('🧹 Clear Closed Trades'):
        st.session_state.tracked_trades = [t for t in st.session_state.tracked_trades if 'Closed' not in t['status']]
        save_portfolio(st.session_state.tracked_trades)
        st.success("Cleaned!")
        
    if st.button('🧨 Reset All'):
        st.session_state.tracked_trades = []
        save_portfolio([])
        st.success("Reset Complete!")

tab3, tab_trend, tab4 = st.tabs(["🐋 Scalping (SMC - FVG)", "🚀 Trend (Squeeze Momentum)", "💼 محفظتي (دائمة)"])

with tab3:
    st.info("🐋 صفقات الأموال الذكية (SMC) - الدخول عند إعادة اختبار فجوات القيمة العادلة (FVG).")
    if not st.session_state.scalping_opps:
        st.warning("جاري تتبع فجوات الحيتان (لا توجد مناطق FVG نشطة الآن)...")
    else:
        for i, opp in enumerate(st.session_state.scalping_opps, 1):
            st.markdown(f"**{opp['symbol']}** | {opp['direction']} | دخول: {opp['price']} | TP1: `{opp['tp1']}` | TP2: `{opp['tp2']}` | وقف: `{opp['sl']}`")
            if st.button(f"➕ Add SMC Trade", key=f"sc_{i}_{opp['symbol']}"): track_trade(opp, 'SMC FVG')

with tab_trend:
    st.info("🚀 صفقات الانفجار السعري (Squeeze Breakout) - اقتناص السعر فور خروجه من التذبذب.")
    if not st.session_state.trend_opps:
        st.warning("⚠️ السوق إما متذبذب (مضغوط) أو لا يوجد انفجار سعري جديد حالياً. جاري المراقبة...")
    else:
        for i, opp in enumerate(st.session_state.trend_opps, 1):
            st.markdown(f"**{opp['symbol']}** | {opp['direction']} | دخول: {opp['price']} | TP1: `{opp['tp1']}` | TP2: `{opp['tp2']}` | وقف: `{opp['sl']}`")
            if st.button(f"➕ Add Breakout Trade", key=f"tr_{i}_{opp['symbol']}"): track_trade(opp, 'Squeeze Breakout')

with tab4:
    if not st.session_state.tracked_trades: st.warning("Portfolio is Empty.")
    else:
        for t in reversed(st.session_state.tracked_trades):
            status_icon = "⚪"
            if "Active" in t['status']: status_icon = "🟢"
            elif "Secured" in t['status']: status_icon = "🎯"
            elif "TP2" in t['status']: status_icon = "🏆"
            elif "Hit SL" in t['status']: status_icon = "🛑"
            elif "Breakeven" in t['status'] or "Manual" in t['status']: status_icon = "🛡️"
            
            tp1_val = t.get('tp1', t.get('tp', 0))
            tp2_val = t.get('tp2', t.get('tp', 0))
            
            st.markdown(f"**{t['symbol']}** | Type: {t['type']} | {t['direction']} | {status_icon} **{t['status']}**")
            st.markdown(f"Entry: {t['entry']} | TP1: {tp1_val} | TP2: {tp2_val} | SL: {t['sl']}")
            
            if t['status'] == PENDING:
                st.markdown("Status: <span style='color: gray; font-weight: bold;'>Waiting for Entry</span>", unsafe_allow_html=True)
                if st.button('❌ Cancel Order', key=f"cancel_{t['id']}"):
                    cancel_trade_action(t['id'])
                    st.rerun()
            else:
                pnl_val = t.get('pnl_pct', 0.0)
                color_style = "color: green;" if pnl_val >= 0 else "color: red;"
                pnl_text = f"PnL: +{pnl_val}%" if pnl_val >= 0 else f"PnL: {pnl_val}%"
                st.markdown(f"Live PnL: <span style='{color_style} font-weight: bold;'>{pnl_text}</span>", unsafe_allow_html=True)
                
                if t['status'] in [ACTIVE, SECURED]:
                    if st.button('⏹️ Close at Market', key=f"close_{t['id']}"):
                        close_trade_action(t['id'], t['symbol'], t['direction'], t['entry'])
                        st.rerun()
                
            st.markdown("---")

time.sleep(60)
st.rerun()


