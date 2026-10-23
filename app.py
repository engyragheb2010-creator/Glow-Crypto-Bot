import streamlit as st
import ccxt
import pandas as pd
import pandas_ta as ta
import time

st.set_page_config(page_title="Glow Crypto Dashboard", layout="wide")
st.title("🌟 Glow Crypto Dashboard (Breakout & SMC)")

exchange = ccxt.okx()

def analyze_crypto(symbol):
    try:
        # 1. جلب بيانات 4 ساعات لتحديد الاتجاه العام (الترند)
        bars_4h = exchange.fetch_ohlcv(symbol, timeframe='4h', limit=250)
        df_4h = pd.DataFrame(bars_4h, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
        df_4h['ema200'] = ta.ema(df_4h['close'], length=200)
        
        last_4h = df_4h.iloc[-1]
        trend_up = last_4h['close'] > last_4h['ema200']
        trend_down = last_4h['close'] < last_4h['ema200']
        
        trend_text = "Up ⬆️" if trend_up else "Down ⬇️" if trend_down else "Neutral ↔️"

        # 2. جلب بيانات 5 دقائق لتحديد نقطة الدخول (Breakout & SMC FVG)
        bars_5m = exchange.fetch_ohlcv(symbol, timeframe='5m', limit=100)
        df_5m = pd.DataFrame(bars_5m, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
        
        # مؤشر Squeeze (للانفجار السعري / Breakout)
        df_5m[['bb_lower', 'bb_mid', 'bb_upper']] = ta.bbands(df_5m['close'], length=20).iloc[:, :3]
        
        # السطر اللي تم تصحيحه وإضافة High و Low
        kc = ta.kc(df_5m['high'], df_5m['low'], df_5m['close'], length=20, scalar=1.5)
        df_5m['kc_lower'] = kc.iloc[:, 0]
        df_5m['kc_upper'] = kc.iloc[:, 2]
        
        df_5m['sqz_on'] = (df_5m['bb_lower'] > df_5m['kc_lower']) & (df_5m['bb_upper'] < df_5m['kc_upper'])
        df_5m['sqz_off'] = (df_5m['bb_lower'] < df_5m['kc_lower']) & (df_5m['bb_upper'] > df_5m['kc_upper'])
        df_5m['sqz_fired'] = df_5m['sqz_on'].shift(1) & df_5m['sqz_off']
        
        # SMC FVG (Fair Value Gap)
        df_5m['fvg_bull'] = (df_5m['low'] > df_5m['high'].shift(2)) & (df_5m['close'].shift(1) > df_5m['open'].shift(1))
        df_5m['fvg_bear'] = (df_5m['high'] < df_5m['low'].shift(2)) & (df_5m['close'].shift(1) < df_5m['open'].shift(1))
        
        last_5m = df_5m.iloc[-1]
        current_price = last_5m['close']
        
        # تحديد الإشارة
        signal = "⏳ WAIT (انتظار)"
        signal_color = "gray"
        
        # شروط الشراء: ترند صاعد 4 ساعات + (انفجار سعري 5 دقايق أو فجوة شرائية)
        if trend_up and (last_5m['fvg_bull'] or last_5m['sqz_fired']):
            signal = "🟢 BUY (شراء)"
            signal_color = "green"
            
        # شروط البيع: ترند هابط 4 ساعات + (انفجار سعري 5 دقايق أو فجوة بيعية)
        elif trend_down and (last_5m['fvg_bear'] or last_5m['sqz_fired']):
            signal = "🔴 SELL (بيع)"
            signal_color = "red"
            
        return current_price, trend_text, signal, signal_color
        
    except Exception as e:
        return None, None, f"Error: {str(e)}", "red"

symbols = ['BTC/USDT', 'ETH/USDT', 'BNB/USDT', 'SOL/USDT']

if st.button("🔄 تحديث بيانات السوق الآن"):
    cols = st.columns(4)
    for i, sym in enumerate(symbols):
        price, trend, signal, color = analyze_crypto(sym)
        with cols[i]:
            st.subheader(sym)
            if price is not None:
                st.write(f"**السعر:** {price}$")
                st.write(f"**ترند 4h:** {trend}")
                st.markdown(f"<h5 style='color: {color};'>{signal}</h5>", unsafe_allow_html=True)
            else:
                st.error(signal)
        time.sleep(0.2) 

st.write("---")
st.write("الاستراتيجية: الاتجاه من فريم 4 ساعات + الدخول (Breakout & SMC) من فريم 5 دقائق")

