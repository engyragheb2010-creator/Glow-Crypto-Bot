import streamlit as st
import ccxt
import pandas as pd
import pandas_ta as ta

st.set_page_config(page_title="Glow Crypto Dashboard", layout="wide")

# تهيئة ذاكرة المحفظة
if 'portfolio' not in st.session_state:
    st.session_state.portfolio = []

# ربط منصة OKX وجلب أسعار الفيوترز (Perpetual)
exchange = ccxt.okx({
    'options': {'defaultType': 'swap'}
})
# إضافة :USDT لسحب عقود الفيوترز
symbols = ['BTC/USDT:USDT', 'ETH/USDT:USDT', 'BNB/USDT:USDT', 'SOL/USDT:USDT']

st.title("🌟 Glow Crypto Dashboard (Futures & Auto-SL)")

# زرار التحديث
if st.button("🔄 تحديث الأسعار الآن"):
    pass 

def add_trade(symbol, entry_price, trade_type, direction):
    # إعدادات الأهداف والاستوب لوس
    tp1_pct = 0.01  # 1% للهدف الأول
    tp2_pct = 0.02  # 2% للهدف الثاني
    sl_pct = 0.01   # 1% للاستوب لوس
    
    # حساب الأرقام بناءً على الشراء أو البيع
    if "BUY" in direction:
        tp1 = entry_price * (1 + tp1_pct)
        tp2 = entry_price * (1 + tp2_pct)
        sl = entry_price * (1 - sl_pct)
    else: # SELL
        tp1 = entry_price * (1 - tp1_pct)
        tp2 = entry_price * (1 - tp2_pct)
        sl = entry_price * (1 + sl_pct)
        
    st.session_state.portfolio.append({
        'symbol': symbol,
        'entry_price': entry_price,
        'type': trade_type,
        'direction': direction,
        'tp1': tp1,
        'tp2': tp2,
        'sl': sl,
        'sl_moved': False # مؤشر بيعرفنا هل الاستوب اتنقل ولا لسه
    })

def close_trade(index):
    st.session_state.portfolio.pop(index)

def analyze_crypto(symbol):
    try:
        # فريم 4 ساعات (الترند)
        bars_4h = exchange.fetch_ohlcv(symbol, timeframe='4h', limit=250)
        df_4h = pd.DataFrame(bars_4h, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
        df_4h['ema200'] = ta.ema(df_4h['close'], length=200)
        trend_up = df_4h.iloc[-1]['close'] > df_4h.iloc[-1]['ema200']
        trend_down = df_4h.iloc[-1]['close'] < df_4h.iloc[-1]['ema200']

        # فريم 5 دقائق (الإشارات)
        bars_5m = exchange.fetch_ohlcv(symbol, timeframe='5m', limit=100)
        df_5m = pd.DataFrame(bars_5m, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
        
        # مؤشر Squeeze
        df_5m[['bb_lower', 'bb_mid', 'bb_upper']] = ta.bbands(df_5m['close'], length=20).iloc[:, :3]
        kc = ta.kc(df_5m['high'], df_5m['low'], df_5m['close'], length=20, scalar=1.5)
        df_5m['kc_lower'] = kc.iloc[:, 0]
        df_5m['kc_upper'] = kc.iloc[:, 2]
        df_5m['sqz_on'] = (df_5m['bb_lower'] > df_5m['kc_lower']) & (df_5m['bb_upper'] < df_5m['kc_upper'])
        df_5m['sqz_off'] = (df_5m['bb_lower'] < df_5m['kc_lower']) & (df_5m['bb_upper'] > df_5m['kc_upper'])
        df_5m['sqz_fired'] = df_5m['sqz_on'].shift(1) & df_5m['sqz_off']
        
        # مؤشر SMC FVG 
        df_5m['fvg_bull'] = (df_5m['low'] > df_5m['high'].shift(2)) & (df_5m['close'].shift(1) > df_5m['open'].shift(1))
        df_5m['fvg_bear'] = (df_5m['high'] < df_5m['low'].shift(2)) & (df_5m['close'].shift(1) < df_5m['open'].shift(1))
        
        price = df_5m.iloc[-1]['close']
        last_5m = df_5m.iloc[-1]
        
        sqz_signal = "⏳ WAIT"
        if trend_up and last_5m['sqz_fired']: sqz_signal = "🟢 BUY"
        elif trend_down and last_5m['sqz_fired']: sqz_signal = "🔴 SELL"
            
        brk_signal = "⏳ WAIT"
        if trend_up and last_5m['fvg_bull']: brk_signal = "🟢 BUY"
        elif trend_down and last_5m['fvg_bear']: brk_signal = "🔴 SELL"
            
        return price, sqz_signal, brk_signal
    except Exception as e:
        return None, "Error", "Error"

# تقسيم الشاشة
col1, col2, col3 = st.columns(3)

with col1:
    st.header("💥 Breakout & SMC")
with col2:
    st.header("🗜️ Squeeze")
with col3:
    st.header("💼 المحفظة الذكية (الفيوترز)")

# عرض الإشارات وزراير الإضافة
for sym in symbols:
    price, sqz_signal, brk_signal = analyze_crypto(sym)
    
    if price is None:
        continue
        
    with col1:
        st.markdown(f"**{sym.replace(':USDT','')}** - {price}$")
        st.write(f"الإشارة: {brk_signal}")
        if "BUY" in brk_signal or "SELL" in brk_signal:
            if st.button(f"أضف للمحفظة 💥", key=f"brk_{sym}"):
                add_trade(sym, price, "Breakout/SMC", brk_signal)
                st.rerun()
        st.write("---")

    with col2:
        st.markdown(f"**{sym.replace(':USDT','')}** - {price}$")
        st.write(f"الإشارة: {sqz_signal}")
        if "BUY" in sqz_signal or "SELL" in sqz_signal:
            if st.button(f"أضف للمحفظة 🗜️", key=f"sqz_{sym}"):
                add_trade(sym, price, "Squeeze", sqz_signal)
                st.rerun()
        st.write("---")

# عرض المحفظة وإدارة الصفقات
with col3:
    if len(st.session_state.portfolio) == 0:
        st.info("لا توجد صفقات مفتوحة حالياً.")
    else:
        for i, trade in enumerate(st.session_state.portfolio):
            st.markdown(f"#### {trade['symbol'].replace(':USDT','')}")
            st.write(f"**الإشارة:** {trade['direction']} ({trade['type']})")
            st.write(f"**سعر الدخول:** {trade['entry_price']}$")
            
            try:
                ticker = exchange.fetch_ticker(trade['symbol'])
                current_price = ticker['last']
                
                # --- نظام تأمين الصفقة (نقل الاستوب لسعر الدخول) ---
                if not trade['sl_moved']:
                    if "BUY" in trade['direction'] and current_price >= trade['tp1']:
                        st.session_state.portfolio[i]['sl'] = trade['entry_price']
                        st.session_state.portfolio[i]['sl_moved'] = True
                    elif "SELL" in trade['direction'] and current_price <= trade['tp1']:
                        st.session_state.portfolio[i]['sl'] = trade['entry_price']
                        st.session_state.portfolio[i]['sl_moved'] = True
                
                # حساب نسبة الربح/الخسارة
                if "BUY" in trade['direction']:
                    pnl = ((current_price - trade['entry_price']) / trade['entry_price']) * 100
                else: 
                    pnl = ((trade['entry_price'] - current_price) / trade['entry_price']) * 100
                    
                pnl_color = "green" if pnl > 0 else "red"
                
                st.markdown(f"**السعر الحالي:** {current_price}$")
                st.markdown(f"**الربح/الخسارة:** <span style='color:{pnl_color}; font-size:18px;'><b>{pnl:.2f}%</b></span>", unsafe_allow_html=True)
                
                # عرض الأهداف والاستوب لوس
                st.write(f"🎯 **Target 1:** {trade['tp1']:.2f}$")
                st.write(f"🚀 **Target 2:** {trade['tp2']:.2f}$")
                
                if trade['sl_moved']:
                    st.success(f"✅ تم تأمين الصفقة! (SL = Entry: {trade['sl']:.2f}$)")
                else:
                    st.warning(f"🛑 **Stop Loss:** {trade['sl']:.2f}$")
                    
            except:
                st.write("جاري تحديث السعر...")
                
            if st.button("❌ إغلاق الصفقة", key=f"close_{i}"):
                close_trade(i)
                st.rerun()
            st.write("---")
