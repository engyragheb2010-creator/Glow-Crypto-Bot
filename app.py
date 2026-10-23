import streamlit as st
import ccxt
import pandas as pd
import pandas_ta as ta

st.set_page_config(page_title="Glow Crypto Dashboard", layout="wide")
st.title("🌟 Glow Crypto Dashboard (OKX)")

# ربط منصة OKX
exchange = ccxt.okx()

def analyze_crypto(symbol):
    try:
        # جلب البيانات
        bars = exchange.fetch_ohlcv(symbol, timeframe='15m', limit=200)
        df = pd.DataFrame(bars, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
        
        # حساب EMA 200
        df['ema200'] = ta.ema(df['close'], length=200)
        
        # حساب Squeeze
        df[['bb_lower', 'bb_mid', 'bb_upper']] = ta.bbands(df['close'], length=20).iloc[:, :3]
        kc = ta.kc(df['close'], length=20, scalar=1.5)
        df['kc_lower'] = kc.iloc[:, 0]
        df['kc_upper'] = kc.iloc[:, 2]
        
        df['sqz_on'] = (df['bb_lower'] > df['kc_lower']) & (df['bb_upper'] < df['kc_upper'])
        df['sqz_off'] = (df['bb_lower'] < df['kc_lower']) & (df['bb_upper'] > df['kc_upper'])
        df['sqz_fired'] = df['sqz_on'].shift(1) & df['sqz_off']
        
        # حساب SMC FVG
        df['fvg_bull'] = (df['low'] > df['high'].shift(2)) & (df['close'].shift(1) > df['open'].shift(1))
        df['fvg_bear'] = (df['high'] < df['low'].shift(2)) & (df['close'].shift(1) < df['open'].shift(1))
        
        last = df.iloc[-1]
        
        # تحديد الاتجاه والإشارات
        trend = "Up ⬆️" if last['close'] > last['ema200'] else "Down ⬇️"
        
        signal = "⏳ WAIT"
        signal_color = "gray"
        
        if last['close'] > last['ema200'] and (last['fvg_bull'] or last['sqz_fired']):
            signal = "🟢 BUY (شراء)"
            signal_color = "green"
        elif last['close'] < last['ema200'] and (last['fvg_bear'] or last['sqz_fired']):
            signal = "🔴 SELL (بيع)"
            signal_color = "red"
            
        return last['close'], trend, signal, signal_color
        
    except Exception as e:
        return None, None, "Error", "red"

# العملات المطلوبة
symbols = ['BTC/USDT', 'ETH/USDT', 'BNB/USDT', 'SOL/USDT']

if st.button("🔄 تحديث بيانات السوق الآن"):
    cols = st.columns(4)
    for i, sym in enumerate(symbols):
        price, trend, signal, color = analyze_crypto(sym)
        with cols[i]:
            st.subheader(sym)
            st.write(f"**السعر:** {price}$")
            st.write(f"**الاتجاه:** {trend}")
            st.markdown(f"<h3 style='color: {color};'>{signal}</h3>", unsafe_allow_html=True)

st.write("---")
st.write("البيانات تأتي مباشرة من منصة OKX - الإطار الزمني: 15 دقيقة")
