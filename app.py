import streamlit as st
import ccxt
import time
import pandas as pd
import pandas_ta as ta

# --- إعدادات الصفحة ---
st.set_page_config(page_title="🐋 Glow Crypto Bot", layout="wide")
st.title("🐋 لوحة تحكم التداول المؤسسي (4H + 5m)")

# --- الاتصال الآمن بالمنصة ---
try:
    exchange = ccxt.okx({
        'apiKey': st.secrets"41e8e6d1-3d2d-4861-b0df-61ccdb79e34b"
        'secret': st.secrets"1FC2FDF62E1F188458144B7700759BC3" 
        'password': st.secrets "Ahmedengy2010@" 
        'enableRateLimit': True,
    })
except Exception:
    st.error("⚠️ يرجى وضع مفاتيح الـ API في إعدادات Streamlit (Secrets).")
    st.stop()

# --- إعدادات الاستراتيجية ---
SYMBOLS = ['BTC/USDT', 'ETH/USDT', 'BNB/USDT', 'SOL/USDT']
TIMEFRAME_TREND = '4h'   
TIMEFRAME_ENTRY = '5m'   
RISK_REWARD_1 = 3        
RISK_REWARD_2 = 6        
POLL_INTERVAL = 60       

if 'active_positions' not in st.session_state:
    st.session_state.active_positions = {}

@st.cache_data(ttl=50)
def get_data(symbol, timeframe, limit=100):
    bars = exchange.fetch_ohlcv(symbol, timeframe, limit=limit)
    df = pd.DataFrame(bars, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
    df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms')
    return df

def get_4h_trend(symbol):
    df = get_data(symbol, TIMEFRAME_TREND)
    df.ta.ema(length=200, append=True)
    if 'EMA_200' not in df.columns: return 'NEUTRAL'
    current_close = df['close'].iloc[-1]
    ema_200 = df['EMA_200'].iloc[-1]
    if current_close > ema_200: return 'BULLISH'
    elif current_close < ema_200: return 'BEARISH'
    return 'NEUTRAL'

def check_entry_signals(symbol, trend):
    df = get_data(symbol, TIMEFRAME_ENTRY)
    df.ta.squeeze(append=True)
    sqz_col = [col for col in df.columns if 'SQZ' in col and 'ON' not in col]
    sqz_on = [col for col in df.columns if 'SQZ_ON' in col]
    if not sqz_col or not sqz_on: return None
    sqz_col, sqz_on = sqz_col[0], sqz_on[0]
    
    signal, strategy, stop_loss = None, None, 0
    entry_price = df['close'].iloc[-1]
    
    # SMC FVG
    bullish_fvg = df['low'].iloc[-2] > df['high'].iloc[-4]
    bearish_fvg = df['high'].iloc[-2] < df['low'].iloc[-4]
    if trend == 'BULLISH' and bullish_fvg:
        signal, strategy, stop_loss = 'LONG', 'SMC FVG', df['low'].iloc[-4]
    elif trend == 'BEARISH' and bearish_fvg:
        signal, strategy, stop_loss = 'SHORT', 'SMC FVG', df['high'].iloc[-4]
        
    # Squeeze Breakout
    squeeze_fired = (df[sqz_on].iloc[-3] == 1) and (df[sqz_on].iloc[-2] == 0)
    momentum_up = df[sqz_col].iloc[-2] > 0 and df[sqz_col].iloc[-2] > df[sqz_col].iloc[-3]
    momentum_down = df[sqz_col].iloc[-2] < 0 and df[sqz_col].iloc[-2] < df[sqz_col].iloc[-3]
    if not signal and squeeze_fired:
        if trend == 'BULLISH' and momentum_up:
            signal, strategy, stop_loss = 'LONG', 'Squeeze Breakout', df['low'].iloc[-2] - (df['high'].iloc[-2] - df['low'].iloc[-2]) * 0.5
        elif trend == 'BEARISH' and momentum_down:
            signal, strategy, stop_loss = 'SHORT', 'Squeeze Breakout', df['high'].iloc[-2] + (df['high'].iloc[-2] - df['low'].iloc[-2]) * 0.5

    if signal:
        risk = abs(entry_price - stop_loss)
        if risk == 0: return None
        tp1 = entry_price + (risk * RISK_REWARD_1) if signal == 'LONG' else entry_price - (risk * RISK_REWARD_1)
        tp2 = entry_price + (risk * RISK_REWARD_2) if signal == 'LONG' else entry_price - (risk * RISK_REWARD_2)
        return {
            'Symbol': symbol, 'Type': strategy, 'Direction': signal,
            'Entry': entry_price, 'SL': stop_loss, 'TP1': tp1, 'TP2': tp2,
            'Status': 'Active', 'Secured': False, 'PnL %': 0.0
        }
    return None

symbols_to_remove = []
for symbol in SYMBOLS:
    if symbol not in st.session_state.active_positions:
        trend_4h = get_4h_trend(symbol)
        trade = check_entry_signals(symbol, trend_4h)
        if trade:
            st.session_state.active_positions[symbol] = trade
            st.success(f"🚨 فرصة جديدة: {symbol} | {trade['Type']} | {trade['Direction']}")

for symbol, pos in st.session_state.active_positions.items():
    try:
        ticker = exchange.fetch_ticker(symbol)
        current_price = ticker['last']
        if pos['Direction'] == 'LONG':
            pos['PnL %'] = round(((current_price - pos['Entry']) / pos['Entry']) * 100, 2)
            if current_price >= pos['TP2']: symbols_to_remove.append(symbol)
            elif current_price >= pos['TP1'] and not pos['Secured']:
                pos['SL'] = pos['Entry']
                pos['Secured'] = True
                pos['Status'] = '🛡️ Secured'
            elif current_price <= pos['SL']: symbols_to_remove.append(symbol)
        elif pos['Direction'] == 'SHORT':
            pos['PnL %'] = round(((pos['Entry'] - current_price) / pos['Entry']) * 100, 2)
            if current_price <= pos['TP2']: symbols_to_remove.append(symbol)
            elif current_price <= pos['TP1'] and not pos['Secured']:
                pos['SL'] = pos['Entry']
                pos['Secured'] = True
                pos['Status'] = '🛡️ Secured'
            elif current_price >= pos['SL']: symbols_to_remove.append(symbol)
    except Exception:
        pass

for sym in symbols_to_remove:
    del st.session_state.active_positions[sym]

st.subheader("💼 المحفظة النشطة")
if st.session_state.active_positions:
    st.dataframe(pd.DataFrame(st.session_state.active_positions.values()), use_container_width=True)
else:
    st.info("⏳ جاري مراقبة السوق للبحث عن فرص (4H + 5m)...")

st.write(f"🔄 **تحديث تلقائي:** {pd.Timestamp.now().strftime('%H:%M:%S')}")
time.sleep(POLL_INTERVAL)
st.rerun()

