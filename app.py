import streamlit as st
import ccxt
import pandas as pd
import pandas_ta as ta
import time

st.set_page_config(page_title="Glow Crypto Dashboard", layout="wide")

@st.cache_resource
def get_portfolio():
    return []

portfolio = get_portfolio()

exchange = ccxt.okx({
    'options': {'defaultType': 'swap'},
    'enableRateLimit': True 
})
# تقدري تزودي أو تعدلي العملات من هنا
symbols = ['BTC/USDT:USDT', 'ETH/USDT:USDT', 'BNB/USDT:USDT', 'SOL/USDT:USDT']

# --- القائمة الجانبية (Sidebar) ---
st.sidebar.title("⚙️ Bot Settings")
st.sidebar.write("Choose the strictness level:")
trading_mode = st.sidebar.radio(
    "Trading Mode", 
    ["🎯 Pro Sniper (Safest)", "🔥 Action Mode (Faster)"]
)
st.sidebar.write("---")
if "Pro" in trading_mode:
    st.sidebar.info("**Pro Sniper (Updated):** Requires 1H and 15m trends to match perfectly + High Volume. (4H removed for faster adaptation to market pumps).")
else:
    st.sidebar.warning("**Action Mode:** Relies only on the 15m trend for faster entries. Higher risk of fakeouts.")

st.title(f"🌟 Glow Crypto Dashboard - {trading_mode[:2]}")

if st.button("🔄 Update Prices Now"):
    pass 

def add_trade(symbol, entry_price, trade_type, direction, mode):
    tp1_pct = 0.01  
    tp2_pct = 0.02  
    sl_pct = 0.01   
    
    if "BUY" in direction:
        tp1 = entry_price * (1 + tp1_pct)
        tp2 = entry_price * (1 + tp2_pct)
        sl = entry_price * (1 - sl_pct)
    else: 
        tp1 = entry_price * (1 - tp1_pct)
        tp2 = entry_price * (1 - tp2_pct)
        sl = entry_price * (1 + sl_pct)
        
    portfolio.append({
        'symbol': symbol,
        'entry_price': entry_price,
        'type': trade_type,
        'direction': direction,
        'mode': mode,
        'tp1': tp1,
        'tp2': tp2,
        'sl': sl,
        'sl_moved': False,
        'status': 'active', 
        'exit_price': 0.0   
    })

def close_trade(index):
    portfolio.pop(index)

def analyze_crypto(symbol, current_mode):
    try:
        # 1. 1H Trend (المؤشر الرئيسي الجديد بدل الـ 4 ساعات)
        bars_1h = exchange.fetch_ohlcv(symbol, timeframe='1h', limit=250)
        df_1h = pd.DataFrame(bars_1h, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
        df_1h['ema200'] = ta.ema(df_1h['close'], length=200)
        trend_1h_up = df_1h.iloc[-1]['close'] > df_1h.iloc[-1]['ema200']
        time.sleep(0.1)
        
        # 2. 15m Trend (مؤشر التأكيد والـ Action)
        bars_15m = exchange.fetch_ohlcv(symbol, timeframe='15m', limit=250)
        df_15m = pd.DataFrame(bars_15m, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
        df_15m['ema200'] = ta.ema(df_15m['close'], length=200)
        trend_15m_up = df_15m.iloc[-1]['close'] > df_15m.iloc[-1]['ema200']
        time.sleep(0.1)

        # 3. 5m Entry & Volume (نقطة الدخول والسيولة)
        bars_5m = exchange.fetch_ohlcv(symbol, timeframe='5m', limit=100)
        df_5m = pd.DataFrame(bars_5m, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
        df_5m['vol_sma'] = ta.sma(df_5m['volume'], length=20)
        
        # --- تحديد شروط الاتجاه بالخلطة الجديدة ---
        if "Pro" in current_mode:
            trend_up = trend_1h_up and trend_15m_up
            trend_down = (not trend_1h_up) and (not trend_15m_up)
        else:
            trend_up = trend_15m_up
            trend_down = not trend_15m_up

        # Squeeze Logic
        df_5m[['bb_lower', 'bb_mid', 'bb_upper']] = ta.bbands(df_5m['close'], length=20).iloc[:, :3]
        kc = ta.kc(df_5m['high'], df_5m['low'], df_5m['close'], length=20, scalar=1.5)
        df_5m['kc_lower'] = kc.iloc[:, 0]
        df_5m['kc_upper'] = kc.iloc[:, 2]
        df_5m['sqz_on'] = (df_5m['bb_lower'] > df_5m['kc_lower']) & (df_5m['bb_upper'] < df_5m['kc_upper'])
        df_5m['sqz_off'] = (df_5m['bb_lower'] < df_5m['kc_lower']) & (df_5m['bb_upper'] > df_5m['kc_upper'])
        df_5m['sqz_fired'] = df_5m['sqz_on'].shift(1) & df_5m['sqz_off']
        
        # Breakout/SMC Logic
        df_5m['fvg_bull'] = (df_5m['low'] > df_5m['high'].shift(2)) & (df_5m['close'].shift(1) > df_5m['open'].shift(1))
        df_5m['fvg_bear'] = (df_5m['high'] < df_5m['low'].shift(2)) & (df_5m['close'].shift(1) < df_5m['open'].shift(1))
        
        last_5m = df_5m.iloc[-1]
        price = last_5m['close']
        high_volume = last_5m['volume'] > last_5m['vol_sma']

        # Debug String (تم التحديث عشان يظهر 1H و 15m بس)
        d_1h = "🟢" if trend_1h_up else "🔴"
        d_15m = "🟢" if trend_15m_up else "🔴"
        d_vol = "🔥" if high_volume else "❄️"
        debug_info = f"1H:{d_1h} | 15m:{d_15m} | Vol:{d_vol}"

        sqz_signal = "⏳ WAIT"
        if trend_up and last_5m['sqz_fired'] and high_volume: sqz_signal = "🟢 BUY"
        elif trend_down and last_5m['sqz_fired'] and high_volume: sqz_signal = "🔴 SELL"
            
        brk_signal = "⏳ WAIT"
        if trend_up and last_5m['fvg_bull'] and high_volume: brk_signal = "🟢 BUY"
        elif trend_down and last_5m['fvg_bear'] and high_volume: brk_signal = "🔴 SELL"
            
        return price, sqz_signal, brk_signal, debug_info
    except Exception as e:
        st.error(f"⚠️ Error loading {symbol}: {e}")
        return None, "Error", "Error", "Error"

col1, col2, col3 = st.columns([1, 1, 1.2])

with col1:
    st.header("💥 Breakout/SMC")
with col2:
    st.header("🗜️ Squeeze")
with col3:
    st.header("💼 Smart Portfolio")

for sym in symbols:
    price, sqz_signal, brk_signal, debug_info = analyze_crypto(sym, trading_mode)
    
    if price is None:
        continue
        
    is_brk_active = any(t['symbol'] == sym and t['type'] == "Breakout/SMC" and t.get('status') == 'active' for t in portfolio)
    is_sqz_active = any(t['symbol'] == sym and t['type'] == "Squeeze" and t.get('status') == 'active' for t in portfolio)
        
    with col1:
        st.markdown(f"### {sym.replace(':USDT','')}")
        st.markdown(f"**💰 Price:** ${price}")
        st.info(f"📊 {debug_info}") 
        st.write(f"**Signal:** {brk_signal}")
        
        if "BUY" in brk_signal or "SELL" in brk_signal:
            if is_brk_active:
                st.caption("🔒 Already Running")
            else:
                mode_label = "🎯 Pro" if "Pro" in trading_mode else "🔥 Action"
                st.button(f"Add 💥", key=f"brk_{sym}", on_click=add_trade, args=(sym, price, "Breakout/SMC", brk_signal, mode_label))
        st.write("---")

    with col2:
        st.markdown(f"### {sym.replace(':USDT','')}")
        st.markdown(f"**💰 Price:** ${price}")
        st.info(f"📊 {debug_info}") 
        st.write(f"**Signal:** {sqz_signal}")
        
        if "BUY" in sqz_signal or "SELL" in sqz_signal:
            if is_sqz_active:
                st.caption("🔒 Already Running")
            else:
                mode_label = "🎯 Pro" if "Pro" in trading_mode else "🔥 Action"
                st.button(f"Add 🗜️", key=f"sqz_{sym}", on_click=add_trade, args=(sym, price, "Squeeze", sqz_signal, mode_label))
        st.write("---")

with col3:
    if len(portfolio) == 0:
        st.info("No open trades currently.")
    else:
        for i, trade in enumerate(portfolio):
            
            display_price = trade['entry_price'] 
            
            if trade.get('status', 'active') == 'active':
                try:
                    ticker = exchange.fetch_ticker(trade['symbol'])
                    current_price = ticker['last']
                    
                    # تأمين الصفقة بعد الهدف الأول
                    if not trade['sl_moved']:
                        if "BUY" in trade['direction'] and current_price >= trade['tp1']:
                            trade['sl'] = trade['entry_price']
                            trade['sl_moved'] = True
                        elif "SELL" in trade['direction'] and current_price <= trade['tp1']:
                            trade['sl'] = trade['entry_price']
                            trade['sl_moved'] = True
                    
                    # ضرب الأهداف أو الاستوب
                    if "BUY" in trade['direction']:
                        if current_price >= trade['tp2']:
                            trade['status'] = 'hit_tp2'
                            trade['exit_price'] = trade['tp2'] 
                        elif current_price <= trade['sl']:
                            trade['status'] = 'hit_sl'
                            trade['exit_price'] = trade['sl']  
                    else:
                        if current_price <= trade['tp2']:
                            trade['status'] = 'hit_tp2'
                            trade['exit_price'] = trade['tp2']
                        elif current_price >= trade['sl']:
                            trade['status'] = 'hit_sl'
                            trade['exit_price'] = trade['sl']
                            
                    display_price = current_price if trade['status'] == 'active' else trade['exit_price']
                except:
                    display_price = trade['entry_price']
            else:
                display_price = trade['exit_price']
                
            # حساب الخسارة أو المكسب
            if "BUY" in trade['direction']:
                pnl = ((display_price - trade['entry_price']) / trade['entry_price']) * 100
            else: 
                pnl = ((trade['entry_price'] - display_price) / trade['entry_price']) * 100
            
            pnl_color = "green" if pnl > 0 else "red"
            
            if trade['status'] == 'hit_tp2':
                title_status = "🎉 Won"
            elif trade['status'] == 'hit_sl':
                title_status = "🛡️ Break-even" if trade['sl_moved'] else "🛑 Lost"
            else:
                title_status = f"{pnl:.2f}%"
                
            strat_icon = "💥" if "Breakout" in trade['type'] else "🗜️"
            expander_title = f"{trade['symbol'].replace(':USDT','')} | {trade['mode']} | {strat_icon} | {title_status}"
            
            with st.expander(expander_title, expanded=False):
                st.write(f"**Mode:** {trade['mode']}")
                st.write(f"**Strategy:** {trade['type']}")
                st.write(f"**Direction:** {trade['direction']}")
                st.write(f"**Entry Price:** ${trade['entry_price']}")
                
                if trade['status'] == 'active':
                    st.markdown(f"**Live Price:** ${display_price}")
                else:
                    st.markdown(f"**Exit Price:** ${display_price}")
                    
                st.markdown(f"**PnL:** <span style='color:{pnl_color}; font-size:18px;'><b>{pnl:.2f}%</b></span>", unsafe_allow_html=True)
                
                if trade['status'] == 'hit_tp2':
                    st.success("🎉 **Status: Hit Target 2**")
                elif trade['status'] == 'hit_sl':
                    if trade['sl_moved']:
                        st.warning("🛡️ **Status: Closed at Entry (Break-even)**")
                    else:
                        st.error("🛑 **Status: Hit Stop Loss**")
                else:
                    st.write(f"🎯 **Target 1:** ${trade['tp1']:.2f}")
                    st.write(f"🚀 **Target 2:** ${trade['tp2']:.2f}")
                    if trade['sl_moved']:
                        st.success(f"✅ Trade Secured! (SL = Entry: ${trade['sl']:.2f})")
                    else:
                        st.warning(f"🛑 **Stop Loss:** ${trade['sl']:.2f}")
                    
                if st.button("❌ Remove Trade", key=f"close_{i}"):
                    close_trade(i)
                    st.rerun()
