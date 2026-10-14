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

def calculate_atr(highs, lows, closes, period=14):
    tr_list = [highs[0] - lows[0]]
    for i in range(1, len(closes)):
        h_l = highs[i] - lows[i]
        h_pc = abs(highs[i] - closes[i-1])
        l_pc = abs(lows[i] - closes[i-1])
        tr_list.append(max(h_l, h_pc, l_pc))
    atr = pd.Series(tr_list).rolling(window=period).mean().iloc[-1]
    return atr if not np.isnan(atr) else (highs[-1] * 0.01)

# 1. استراتيجية السكالبينج: FVG (Fair Value Gap)
def detect_fvg_entry(highs, lows, closes, curr_price):
    # نبحث في آخر 10 شموع عن فجوة سعرية تركها الحيتان
    for i in range(len(closes)-2, len(closes)-10, -1):
        # FVG شرائي (Bullish)
        if lows[i] > highs[i-2]:
            fvg_top = lows[i]
            fvg_bottom = highs[i-2]
            # الدخول لو السعر الحالي نزل يختبر الفجوة
            if fvg_bottom <= curr_price <= fvg_top:
                return "LONG", fvg_bottom
        
        # FVG بيعي (Bearish)
        elif highs[i] < lows[i-2]:
            fvg_bottom = highs[i]
            fvg_top = lows[i-2]
            # الدخول لو السعر الحالي صعد يختبر الفجوة
            if fvg_bottom <= curr_price <= fvg_top:
                return "SHORT", fvg_top
    return None, 0

# 2. استراتيجية التريند: Squeeze Momentum (الانفجار السعري)
def calculate_squeeze(highs, lows, closes, period=20, bb_mult=2.0, kc_mult=1.5):
    df = pd.DataFrame({'high': highs, 'low': lows, 'close': closes})
    df['sma'] = df['close'].rolling(period).mean()
    df['std'] = df['close'].rolling(period).std()
    
    # Bollinger Bands
    df['bb_upper'] = df['sma'] + bb_mult * df['std']
    df['bb_lower'] = df['sma'] - bb_mult * df['std']
    
    # Keltner Channel
    df['tr'] = np.maximum(df['high'] - df['low'], np.maximum(abs(df['high'] - df['close'].shift(1)), abs(df['low'] - df['close'].shift(1))))
    df['atr'] = df['tr'].rolling(period).mean()
    df['kc_upper'] = df['sma'] + kc_mult * df['atr']
    df['kc_lower'] = df['sma'] - kc_mult * df['atr']
    
    # Squeeze Condition (مضغوط = داخل القناة، انفجار = خارج القناة)
    df['squeeze_on'] = (df['bb_lower'] > df['kc_lower']) & (df['bb_upper'] < df['kc_upper'])
    df['squeeze_off'] = (df['bb_lower'] < df['kc_lower']) | (df['bb_upper'] > df['kc_upper'])
    df['mom'] = df['close'] - df['sma'] # اتجاه العزم
    
    is_sq_off = df['squeeze_off'].iloc[-1]
    was_sq_on = df['squeeze_on'].iloc[-2] or df['squeeze_on'].iloc[-3] # كان مضغوط وبدأ ينفجر
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
        if t['symbol'] == opp['symbol'] and t['status'] in ['⏳ معلقة', '🟢 نشطة', '🎯 تم تحقيق TP1 (مؤمنة)']:
            st.toast(f"الصفقة موجودة بالفعل!")
            return
    new_trade = {
        'id': f"{opp['symbol']}_{time.time()}", 'symbol': opp['symbol'], 'type': trade_type,
        'direction': opp.get('direction', '🟢 LONG'), 'entry': opp['buy'], 
        'tp1': opp['tp1'], 'tp2': opp['tp2'], 'sl': opp['sl'], 
        'status': '⏳ معلقة', 'secured': False, 'pnl_pct': 0.0
    }
    st.session_state.tracked_trades.append(new_trade)
    save_portfolio(st.session_state.tracked_trades)
    st.toast(f"تمت الإضافة بنجاح للمحفظة!")

active_or_failed_symbols = [
    t['symbol'] for t in st.session_state.tracked_trades 
    if t['status'] in ['⏳ معلقة', '🟢 نشطة', '🎯 تم تحقيق TP1 (مؤمنة)'] or 'خسارة' in t['status'] or 'Hit SL' in t['status']
]

col1, col2 = st.columns([3, 1])
with col1:
    st.success("🐋 البوت يعمل الآن بمنطق الأموال الذكية (SMC) والانفجارات السعرية.")
    
    symbols = ['BTC/USDT', 'ETH/USDT', 'SOL/USDT', 'DOGE/USDT']
    scalp_opps = []
    trend_opps = []
    
    for symbol in symbols:
        try:
            ticker_check = exchange.fetch_ticker(symbol)
            curr_price = ticker_check['last']
            dec = get_decimals(curr_price)
            
            # 1. فحص السكالبينج بـ (FVG - 5m)
            ohlcv_5m = exchange.fetch_ohlcv(symbol, '5m', limit=100)
            h5 = np.array([c[2] for c in ohlcv_5m])
            l5 = np.array([c[3] for c in ohlcv_5m])
            c5 = np.array([c[4] for c in ohlcv_5m])
            curr = c5[-1]
            atr_5 = calculate_atr(h5, l5, c5, 14)
            
            if symbol not in active_or_failed_symbols:
                fvg_dir, fvg_sl_level = detect_fvg_entry(h5, l5, c5, curr)
                
                if fvg_dir == "LONG":
                    scalp_opps.append({
                        'symbol': symbol, 'direction': '🟢 LONG (SMC FVG)', 'price': curr, 'score': 95,
                        'buy': round(curr, dec), 'tp1': round(curr * 1.006, dec), 'tp2': round(curr * 1.015, dec), 
                        'sl': round(min(curr - (1.0 * atr_5), fvg_sl_level * 0.998), dec) # الوقف تحت الفجوة
                    })
                elif fvg_dir == "SHORT":
                    scalp_opps.append({
                        'symbol': symbol, 'direction': '🔴 SHORT (SMC FVG)', 'price': curr, 'score': 95,
                        'buy': round(curr, dec), 'tp1': round(curr * 0.994, dec), 'tp2': round(curr * 0.985, dec), 
                        'sl': round(max(curr + (1.0 * atr_5), fvg_sl_level * 1.002), dec) # الوقف فوق الفجوة
                    })
                
            # 2. فحص التريند بـ (Squeeze Momentum - 15m)
            if symbol not in active_or_failed_symbols:
                ohlcv_15m = exchange.fetch_ohlcv(symbol, '15m', limit=100)
                h15 = np.array([c[2] for c in ohlcv_15m])
                l15 = np.array([c[3] for c in ohlcv_15m])
                c15 = np.array([c[4] for c in ohlcv_15m])
                curr_15 = c15[-1]
                atr_15 = calculate_atr(h15, l15, c15, 14)
                
                is_sq_off, was_sq_on, mom = calculate_squeeze(h15, l15, c15)
                
                # الدخول فقط إذا حدث "انفجار سعري" جديد (كان مضغوط ودلوقتي فك)
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
        except: continue
            
    if (scalp_opps or trend_opps) and (len(scalp_opps) != len(st.session_state.scalping_opps)):
        play_audio_alert()
        
    st.session_state.scalping_opps = scalp_opps
    st.session_state.trend_opps = trend_opps

with col2:
    if st.button('🔄 تحديث المحفظة وفحص الأرباح'):
        with st.spinner('جاري فحص حالة الأوامر والأسعار...'):
            report_logs = []
            for t in st.session_state.tracked_trades:
                if t['status'] in ['⏳ معلقة', '🟢 نشطة', '🎯 تم تحقيق TP1 (مؤمنة)']:
                    try:
                        ticker = exchange.fetch_ticker(t['symbol'])
                        curr = ticker['last']
                        is_long = 'LONG' in t['direction']
                        entry_val = t['entry']
                        
                        if t['status'] == '⏳ معلقة':
                            if (is_long and curr <= entry_val) or (not is_long and curr >= entry_val): 
                                t['status'] = '🟢 نشطة'
                        
                        if t['status'] != '⏳ معلقة':
                            if is_long:
                                pnl = ((curr - entry_val) / entry_val) * 100
                            else:
                                pnl = ((entry_val - curr) / entry_val) * 100
                            t['pnl_pct'] = round(pnl, 2)
                            pnl_label = f"ربح: +{t['pnl_pct']}%" if t['pnl_pct'] >= 0 else f"خسارة: {t['pnl_pct']}%"
                            report_logs.append(f"عملة: {t['symbol']} | السعر: {curr} | الحالة: {pnl_label}")
                        else:
                            t['pnl_pct'] = 0.0
                            report_logs.append(f"عملة: {t['symbol']} | السعر: {curr} | الحالة: ⏳ معلقة في الانتظار")
                        
                        tp1 = t.get('tp1', t.get('tp', 0))
                        tp2 = t.get('tp2', t.get('tp', 0))
                        
                        if t['status'] in ['🟢 نشطة', '🎯 تم تحقيق TP1 (مؤمنة)']:
                            if is_long:
                                if curr >= tp1 and t['status'] == '🟢 نشطة':
                                    t['status'] = '🎯 تم تحقيق TP1 (مؤمنة)'
                                    t['sl'] = entry_val
                                    t['secured'] = True
                                elif curr >= tp2: 
                                    t['status'] = '🎯 ربح كامل (Hit TP2)'
                                elif curr <= t['sl']: 
                                    t['status'] = '🛑 خسارة (Hit SL)' if not t.get('secured', False) else '🛡️ خروج بربح TP1 (بعد تأمين الوقف)'
                            else:
                                if curr <= tp1 and t['status'] == '🟢 نشطة':
                                    t['status'] = '🎯 تم تحقيق TP1 (مؤمنة)'
                                    t['sl'] = entry_val
                                    t['secured'] = True
                                elif curr <= tp2: 
                                    t['status'] = '🎯 ربح كامل (Hit TP2)'
                                elif curr >= t['sl']: 
                                    t['status'] = '🛑 خسارة (Hit SL)' if not t.get('secured', False) else '🛡️ خروج بربح TP1 (بعد تأمين الوقف)'
                    except: pass
            save_portfolio(st.session_state.tracked_trades)
            st.session_state.report_logs = report_logs
        st.success("تم التحديث بنجاح!")
        
    if 'report_logs' in st.session_state and st.session_state.report_logs:
        with st.expander("📊 تقرير الأرباح والفحص الفوري", expanded=True):
            for log in st.session_state.report_logs:
                if "ربح" in log:
                    st.markdown(f"<p style='color:green; font-weight:bold;'>{log}</p>", unsafe_allow_html=True)
                elif "معلقة" in log:
                    st.markdown(f"<p style='color:gray; font-weight:bold;'>{log}</p>", unsafe_allow_html=True)
                else:
                    st.markdown(f"<p style='color:red; font-weight:bold;'>{log}</p>", unsafe_allow_html=True)
        
    st.markdown("---")
    if st.button('🧹 مسح الصفقات المغلقة'):
        st.session_state.tracked_trades = [t for t in st.session_state.tracked_trades if not any(w in t['status'] for w in ['ربح كامل', 'خسارة', 'خروج بربح'])]
        save_portfolio(st.session_state.tracked_trades)
        st.success("تم تنظيف المحفظة!")
        
    if st.button('🧨 تصفير المحفظة بالكامل'):
        st.session_state.tracked_trades = []
        save_portfolio([])
        st.success("تم مسح كل الصفقات!")

tab3, tab_trend, tab4 = st.tabs(["🐋 Scalping (SMC - FVG)", "🚀 Trend (Squeeze Momentum)", "💼 محفظتي (دائمة)"])

with tab3:
    st.info("🐋 صفقات الأموال الذكية (SMC) - الدخول عند إعادة اختبار فجوات القيمة العادلة (FVG).")
    if not st.session_state.scalping_opps:
        st.warning("جاري تتبع فجوات الحيتان (لا توجد مناطق FVG نشطة الآن)...")
    else:
        for i, opp in enumerate(st.session_state.scalping_opps, 1):
            st.markdown(f"**{opp['symbol']}** | {opp['direction']} | دخول: {opp['price']} | TP1: `{opp['tp1']}` | TP2: `{opp['tp2']}` | وقف: `{opp['sl']}`")
            if st.button(f"➕ تتبع SMC", key=f"sc_{i}_{opp['symbol']}"): track_trade(opp, 'SMC FVG')

with tab_trend:
    st.info("🚀 صفقات الانفجار السعري (Squeeze Breakout) - اقتناص السعر فور خروجه من التذبذب.")
    if not st.session_state.trend_opps:
        st.warning("⚠️ السوق إما متذبذب (مضغوط) أو لا يوجد انفجار سعري جديد حالياً. جاري المراقبة...")
    else:
        for i, opp in enumerate(st.session_state.trend_opps, 1):
            st.markdown(f"**{opp['symbol']}** | {opp['direction']} | دخول: {opp['price']} | TP1: `{opp['tp1']}` | TP2: `{opp['tp2']}` | وقف: `{opp['sl']}`")
            if st.button(f"➕ تتبع Breakout", key=f"tr_{i}_{opp['symbol']}"): track_trade(opp, 'Squeeze Breakout')

with tab4:
    if not st.session_state.tracked_trades: st.warning("المحفظة فارغة.")
    else:
        for t in reversed(st.session_state.tracked_trades):
            status_icon = "⚪"
            if "نشطة" in t['status']: status_icon = "🟢"
            elif "TP1" in t['status']: status_icon = "🎯"
            elif "ربح كامل" in t['status']: status_icon = "🏆"
            elif "خسارة" in t['status']: status_icon = "🛑"
            elif "حماية" in t['status'] or "بربح" in t['status']: status_icon = "🛡️"
            
            tp1_val = t.get('tp1', t.get('tp', 0))
            tp2_val = t.get('tp2', t.get('tp', 0))
            
            st.markdown(f"**{t['symbol']}** | نوع: {t['type']} | {t['direction']} | {status_icon} **{t['status']}**")
            st.markdown(f"دخول: {t['entry']} | TP1: {tp1_val} | TP2: {tp2_val} | وقف: {t['sl']}")
            
            if t['status'] == '⏳ معلقة':
                st.markdown("الحالة اللحظية: <span style='color: gray; font-weight: bold;'>في انتظار تفعيل الدخول (معلقة)</span>", unsafe_allow_html=True)
            else:
                pnl_val = t.get('pnl_pct', 0.0)
                color_style = "color: green;" if pnl_val >= 0 else "color: red;"
                pnl_text = f"ربح: +{pnl_val}%" if pnl_val >= 0 else f"خسارة: {pnl_val}%"
                st.markdown(f"الحالة اللحظية: <span style='{color_style} font-weight: bold;'>{pnl_text}</span>", unsafe_allow_html=True)
                
            st.markdown("---")

time.sleep(60)
st.rerun()
