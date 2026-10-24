import streamlit as st
import ccxt
import pandas as pd
import pandas_ta as ta

st.set_page_config(page_title="Glow Crypto Dashboard", layout="wide")

@st.cache_resource
def get_portfolio():
    return []

portfolio = get_portfolio()

exchange = ccxt.okx({
    'options': {'defaultType': 'swap'}
})
symbols = ['BTC/USDT:USDT', 'ETH/USDT:USDT', 'BNB/USDT:USDT', 'SOL/USDT:USDT']

st.title("🌟 Glow Crypto Dashboard (Pro Sniper)")

if st.button("🔄 Update Prices Now"):
    pass 

def add_trade(symbol, entry_price, trade_type, direction):
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
        'tp1': tp1,
        'tp2': tp2,
        'sl': sl,
        'sl_moved': False,
        'status': 'active', 
        'exit_price': 0.0   
    })

def close_trade(index):
    portfolio.pop(index)

def analyze_crypto(symbol):
    try:
        # 1. فريم 4 ساعات
        bars_4h = exchange.fetch_ohlcv(symbol, timeframe='4h', limit=250)
        df_4h = pd.DataFrame(bars_4h, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
        df_4h['ema200'] = ta.ema(df_4h['close'], length=200)
        trend_4h_up = df_4h.iloc[-1]['close'] > df_4h.iloc[-1]['ema200']
        trend_4h_down = df_4h.iloc[-1]['close'] < df_4h.iloc[-1]['ema200']

        # 2. فريم 1 ساعة
        bars_1h = exchange.fetch_ohlcv(symbol, timeframe='1h', limit=250)
        df_1h = pd.DataFrame(bars_1h, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
        df_1h['ema200'] = ta.ema(df_1h['close'], length=200)
        trend_1h_up = df_1h.iloc[-1]['close'] > df_1h.iloc[-1]['ema200']
        trend_1h_down = df_1h.iloc[-1]['close'] < df_1h.iloc[-1]['ema200']

        # 3. فريم 15 دقيقة
        bars_15m = exchange.fetch_ohlcv(symbol, timeframe='15m', limit=250)
        df_15m = pd.DataFrame(bars_15m, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
        df_15m['ema200'] = ta.ema(df_15m['close'], length=200)
        trend_15m_up = df_15m.iloc[-1]['close'] > df_15m.iloc[-1]['ema200']
        trend_15m_down = df_15m.iloc[-1]['close'] < df_15m.iloc[-1]['ema200']

        # --- الفلتر الصارم: الاتجاه الموحد ---
        trend_up_all = trend_4h_up and trend_1h_up and trend_15m_up
        trend_down_all = trend_4h_down and trend_1h_down and trend_15m_down

        # 4. فريم 5 دقايق (نقطة الدخول والسيولة)
        bars_5m = exchange.fetch_ohlcv(symbol, timeframe='5m', limit=100)
        df_5m = pd.DataFrame(bars_5m, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
        
        # --- فلتر السيولة (Volume) ---
        df_5m['vol_sma'] = ta.sma(df_5m['volume'], length=20)
        
        # Squeeze Strategy
        df_5m[['bb_lower', 'bb_mid', 'bb_upper']] = ta.bbands(df_5m['close'], length=20).iloc[:, :3]
        kc = ta.kc(df_5m['high'], df_5m['low'], df_5m['close'], length=20, scalar=1.5)
        df_5m['kc_lower'] = kc.iloc[:, 0]
        df_5m['kc_upper'] = kc.iloc[:, 2]
        df_5m['sqz_on'] = (df_5m['bb_lower'] > df_5m['kc_lower']) & (df_5m['bb_upper'] < df_5m['kc_upper'])
        df_5m['sqz_off'] = (df_5m['bb_lower'] < df_5m['kc_lower']) & (df_5m['bb_upper'] > df_5m['kc_upper'])
        df_5m['sqz_fired'] = df_5m['sqz_on'].shift(1) & df_5m['sqz_off']
        
        # Breakout/SMC Strategy
        df_5m['fvg_bull'] = (df_5m['low'] > df_5m['high'].shift(2)) & (df_5m['close'].shift(1) > df_5m['open'].shift(1))
        df_5m['fvg_bear'] = (df_5m['high'] < df_5m['low'].shift(2)) & (df_5m['close'].shift(1) < df_5m['open'].shift(1))
        
        price = df_5m.iloc[-1]['close']
        last_5m = df_5m.iloc[-1]
        
        # التأكد من إن السيولة الحالية أعلى من المتوسط
        high_volume = last_5m['volume'] > last_5m['vol_sma']
        
        sqz_signal = "⏳ WAIT"
        if trend_up_all and last_5m['sqz_fired'] and high_volume: sqz_signal = "🟢 BUY"
        elif trend_down_all and last_5m['sqz_fired'] and high_volume: sqz_signal = "🔴 SELL"
            
        brk_signal = "⏳ WAIT"
        if trend_up_all and last_5m['fvg_bull'] and high_volume: brk_signal = "🟢 BUY"
        elif trend_down_all and last_5m['fvg_bear'] and high_volume: brk_signal = "🔴 SELL"
            
        return price, sqz_signal, brk_signal
    except Exception as e:
        return None, "Error", "Error"

col1, col2, col3 = st.columns(3)

with col1:
    st.header("💥 Breakout & SMC")
with col2:
    st.header("🗜️ Squeeze")
with col3:
    st.header("💼 Smart Portfolio")

for sym in symbols:
    price, sqz_signal, brk_signal = analyze_crypto(sym)
    
    if price is None:
        continue
        
    is_brk_active = any(t['symbol'] == sym and t['type'] == "Breakout/SMC" and t.get('status') == 'active' for t in portfolio)
    is_sqz_active = any(t['symbol'] == sym and t['type'] == "Squeeze" and t.get('status') == 'active' for t in portfolio)
        
    with col1:
        st.markdown(f"**{sym.replace(':USDT','')}** - ${price}")
        st.write(f"Signal: {brk_signal}")
        if "BUY" in brk_signal or "SELL" in brk_signal:
            if is_brk_active:
                st.caption("🔒 Already Running")
            else:
                if st.button(f"Add to Portfolio 💥", key=f"brk_{sym}"):
                    add_trade(sym, price, "Breakout/SMC", brk_signal)
                    st.rerun()
        st.write("---")

    with col2:
        st.markdown(f"**{sym.replace(':USDT','')}** - ${price}")
        st.write(f"Signal: {sqz_signal}")
        if "BUY" in sqz_signal or "SELL" in sqz_signal:
            if is_sqz_active:
                st.caption("🔒 Already Running")
            else:
                if st.button(f"Add to Portfolio 🗜️", key=f"sqz_{sym}"):
                    add_trade(sym, price, "Squeeze", sqz_signal)
                    st.rerun()
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
                    
                    if not trade['sl_moved']:
                        if "BUY" in trade['direction'] and current_price >= trade['tp1']:
                            trade['sl'] = trade['entry_price']
                            trade['sl_moved'] = True
                        elif "SELL" in trade['direction'] and current_price <= trade['tp1']:
                            trade['sl'] = trade['entry_price']
                            trade['sl_moved'] = True
                    
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
                
            expander_title = f"{trade['symbol'].replace(':USDT','')} | {trade['direction'][:4].strip()} | {title_status}"
            
            with st.expander(expander_title, expanded=False):
                st.write(f"**Strategy:** {trade['type']}")
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
                    
                if st.button("❌ Remove from Portfolio", key=f"close_{i}"):
                    close_trade(i)
                    st.rerun()
