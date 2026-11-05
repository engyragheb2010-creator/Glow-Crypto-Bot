import streamlit as st
from streamlit_autorefresh import st_autorefresh
import ccxt
import pandas as pd
import pandas_ta as ta
import time

# ==========================================
# 1. إعدادات الشاشة الأساسية والتحديث التلقائي
# ==========================================
st.set_page_config(page_title="SMC Sniper Bot", layout="wide")
st.title("🤖 SMC Sniper Bot - Paper Trading")

# تحديث الشاشة كل دقيقة (60,000 ملي ثانية) لضمان متابعة الـ Resting والأهداف
st_autorefresh(interval=60000, limit=None, key="auto_refresh")

# ==========================================
# 2. إعدادات البوت وإدارة المخاطر
# ==========================================
MAX_OPEN_TRADES = 99  # بدون حد أقصى للـ Paper Trading
SYMBOLS = ['BTC/USDT', 'ETH/USDT', 'BNB/USDT', 'SOL/USDT', 'LINK/USDT', 'NEAR/USDT', 'SUI/USDT', 'AVAX/USDT', 'ADA/USDT', 'XRP/USDT']

# إعدادات الذاكرة المؤقتة (Session State)
if 'active_trades' not in st.session_state:
    st.session_state.active_trades = {}
if 'pending_orders' not in st.session_state:
    st.session_state.pending_orders = {}
if 'resting_symbols' not in st.session_state:
    st.session_state.resting_symbols = {}

# ==========================================
# 3. الاتصال بمنصة OKX (Paper Trading)
# ==========================================
try:
    exchange = ccxt.okx({
        'apiKey': 'YOUR_API_KEY',       # ضعي مفاتيح الـ Demo هنا
        'secret': 'YOUR_SECRET_KEY',
        'password': 'YOUR_PASSWORD',
        'enableRateLimit': True,
    })
    exchange.set_sandbox_mode(True)  # تفعيل وضع Paper Trading
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
    """
    دالة تحليل مدرسة الـ SMC (Breakout & FVG)
    ترجع إشارة الشراء، سعر فجوة القيمة العادلة للأوامر المعلقة، وقيمة التذبذب
    """
    if df is None or len(df) < 3:
        return 'NONE', 0.0, 0.0

    last_close = df['close'].iloc[-1]
    prev_high = df['high'].iloc[-2]
    atr_value = df['ATR'].iloc[-1]
    
    is_breakout = last_close > prev_high 
    # حساب منطقة FVG لتعليق الأوامر
    fvg_price = df['low'].iloc[-1] + (df['high'].iloc[-1] - df['low'].iloc[-1]) * 0.5
    
    if is_breakout:
        return 'BUY', fvg_price, atr_value
    return 'NONE', 0.0, 0.0

# ==========================================
# 5. محرك التداول وعرض الشاشة
# ==========================================
st.subheader("📊 Live Market Scanner & Portfolio")

# تقسيم الشاشة لعمودين (صفقات شغالة / أوامر معلقة)
col1, col2 = st.columns(2)
with col1:
    st.markdown("### 🟢 Active Trades")
    for sym, trade in list(st.session_state.active_trades.items()):
        # استخدام :.4f لعرض 4 أرقام عشرية بدقة تامة
        with st.expander(f"{sym} | {trade['mode']} | Entry: ${trade['entry']:.4f}"):
            st.write(f"**Mode:** {trade['mode']}")
            st.write(f"**Entry Price:** ${trade['entry']:.4f}")
            st.write(f"**🎯 Target 1:** ${trade['tp1']:.4f}")
            st.write(f"**🚀 Target 2:** ${trade['tp2']:.4f}")
            st.markdown(f"<span style='color:#ff4b4b'>**🛑 Stop Loss:** ${trade['sl']:.4f}</span>", unsafe_allow_html=True)
            
            # زر يدوي للحذف في حالة التحديثات
            if st.button(f"Remove {sym}", key=f"remove_active_{sym}"):
                del st.session_state.active_trades[sym]
                st.rerun()

with col2:
    st.markdown("### ⏳ Pending Orders (Pro Sniping)")
    for sym, order in list(st.session_state.pending_orders.items()):
        with st.expander(f"{sym} | {order['mode']} | Waiting at FVG: ${order['fvg_price']:.4f}"):
            st.write(f"**Mode:** {order['mode']}")
            st.write(f"**Net Waiting Price:** ${order['fvg_price']:.4f}")
            
            if st.button(f"Cancel {sym}", key=f"cancel_pending_{sym}"):
                del st.session_state.pending_orders[sym]
                st.rerun()

st.markdown("---")

# ==========================================
# 6. لوب فحص السوق واصطياد الفرص
# ==========================================
for symbol in SYMBOLS:
    # تخطي العملة لو شغالة، معلقة، أو في فترة راحة
    if symbol in st.session_state.active_trades or symbol in st.session_state.pending_orders:
        continue
    
    if symbol in st.session_state.resting_symbols:
        # فترة راحة 15 دقيقة (900 ثانية) بعد ضرب الستوب
        if time.time() - st.session_state.resting_symbols[symbol] > 900:
            del st.session_state.resting_symbols[symbol]
        continue

    # جلب البيانات
    df_1h = fetch_data(symbol, '1h')
    df_15m = fetch_data(symbol, '15m')
    
    # تحليل فريم الساعة والـ 15 دقيقة
    signal_1h, fvg_price_1h, atr_1h = analyze_smc(df_1h)
    signal_15m, _, atr_15m = analyze_smc(df_15m)

    current_price = df_15m['close'].iloc[-1] if df_15m is not None else 0
    if current_price == 0:
        continue

    # ----------------------------------------------------
    # اتخاذ القرار (Pro يغلب لو الإشارة على فريم الساعة)
    # ----------------------------------------------------
    if signal_1h == 'BUY':
        try:
            # هنا يتم إرسال Limit Order حقيقي للمنصة مستقبلاً
            st.session_state.pending_orders[symbol] = {
                'fvg_price': fvg_price_1h,
                'atr': atr_1h,
                'mode': '🎯 Pro'
            }
        except Exception as e:
            st.error(f"Error placing Pro order for {symbol}: {e}")

    # لو مفيش إشارة قناص، ندور على إشارة الانفجار (Action)
    elif signal_15m == 'BUY':
        try:
            # --- حل مشكلة خنقة الـ ATR للعملات الرخيصة (Minimum Threshold) ---
            min_target_pct = 0.015  # الحد الأدنى للهدف 1.5%
            
            # حساب الأهداف الافتراضية
            tp1_dist = atr_15m * 1.5
            tp2_dist = atr_15m * 3.0
            sl_dist = atr_15m * 1.5
            
            # لو الـ ATR ضعيف جداً والهدف أقرب من 1.5%، بنفرض الأهداف الإجبارية
            if (tp1_dist / current_price) < min_target_pct:
                tp1_price = current_price * (1 + min_target_pct)            # هدف أول إجباري 1.5%
                tp2_price = current_price * (1 + (min_target_pct * 2.0))    # هدف تاني إجباري 3%
                sl_price = current_price * (1 - min_target_pct)             # ستوب إجباري 1.5%
            else:
                tp1_price = current_price + tp1_dist
                tp2_price = current_price + tp2_dist
                sl_price = current_price - sl_dist

            # تسجيل الصفقة في الشاشة (وهنا يتم وضع Market Order لاحقاً)
            st.session_state.active_trades[symbol] = {
                'entry': current_price,
                'tp1': tp1_price,
                'tp2': tp2_price,
                'sl': sl_price,
                'mode': '🔥 Action'
            }
        except Exception as e:
            st.error(f"Error placing Action order for {symbol}: {e}")
