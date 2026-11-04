import streamlit as st
import ccxt
import pandas as pd
import pandas_ta as ta
import time
from datetime import datetime, timedelta
from streamlit_autorefresh import st_autorefresh

st.set_page_config(page_title="Glow Crypto Dashboard", layout="wide")

# تحديث الشاشة آلياً كل 60 ثانية 
st_autorefresh(interval=60000, limit=None, key="auto_refresh")

@st.cache_resource
def get_portfolio():
    return []

@st.cache_resource
def get_cooldowns():
    return {}

portfolio = get_portfolio()
cooldowns = get_cooldowns()

COOLDOWN_MINUTES = 120 

exchange = ccxt.okx({
    'options': {'defaultType': 'swap'},
    'enableRateLimit': True 
})

@st.cache_data(ttl=15, show_spinner=False)
def fetch_cached_ohlcv(symbol, timeframe, limit):
    time.sleep(0.2) 
    return exchange.fetch_ohlcv(symbol, timeframe=timeframe, limit=limit)

symbols = [
    'BTC/USDT:USDT', 
    'ETH/USDT:USDT', 
    'SOL/USDT:USDT', 
    'BNB/USDT:USDT',
    'XRP/USDT:USDT',
    'ADA/USDT:USDT',
    'AVAX/USDT:USDT',
    'SUI/USDT:USDT',
    'LINK/USDT:USDT',
    'NEAR/USDT:USDT'
]

# --- القائمة الجانبية (Sidebar) ---
st.sidebar.title("⚙️ Bot Settings")
st.sidebar.write("Choose the strictness level:")
trading_mode = st.sidebar.radio(
    "Trading Mode", 
    ["🎯 Pro Sniper (Safest)", "🔥 Action Mode (Faster)"]
)
st.sidebar.write("---")

max_open_trades = st.sidebar.number_input("Max Open Trades", min_value=1, max_value=10, value=10
                                          , step=1)

st.sidebar.write("---")
st.sidebar.subheader("📐 Dynamic ATR Settings")
st.sidebar.info("SL and TP are now based on actual market volatility (ATR) instead of fixed %.")
atr_sl_mult = st.sidebar.slider("Stop Loss (ATR Multiplier)", 1.0, 3.0, 1.5, step=0.1)
atr_tp1_mult = st.sidebar.slider("Target 1 (ATR Multiplier)", 1.0, 3.0, 1.5, step=0.1)
atr_tp2_mult = st.sidebar.slider("Target 2 (ATR Multiplier)", 2.0, 6.0, 3.0, step=0.1)

st.title(f"🌟 Glow Crypto Dashboard - {trading_mode[:2]}")

if st.button("🔄 Force Update Now"):
    pass 

def add_trade(symbol, entry_price, trade_type, direction, mode, atr_value):
    exists = any(t['symbol'] == symbol for t in portfolio)
    if exists:
        return

    # حساب الـ SL و الـ TP بناءً على الـ ATR
    if "BUY" in direction:
        sl = entry_price - (atr_value * atr_sl_mult)
        tp1 = entry_price + (atr_value * atr_tp1_mult)
        tp2 = entry_price + (atr_value * atr_tp2_mult)
    else: 
        sl = entry_price + (atr_value * atr_sl_mult)
        tp1 = entry_price - (atr_value * atr_tp1_mult)
        tp2 = entry_price - (atr_value * atr_tp2_mult)
        
    portfolio.append({
        'symbol': symbol,
        'entry_price': entry_price,
        'type': trade_type,
        'direction': direction,
        'mode': mode,
        'atr_used': atr_value, # حفظ قيمة الـ ATR اللي دخلنا بيها
        'tp1': tp1,
        'tp2': tp2,
        'sl': sl,
        'sl_moved': False,
        'tp1_executed': False,  
        'status': 'active', 
        'exit_price': 0.0,
        'realized_pnl': 0.0     
    })

def close_trade(index):
    trade = portfolio[index]
    if trade.get('status', 'active') == 'active':
        cooldowns[trade['symbol']] = datetime.now() 
    portfolio.pop(index)

def analyze_crypto(symbol, current_mode):
    try:
        bars_1h = fetch_cached_ohlcv(symbol, timeframe='1h', limit=250)
        df_1h = pd.DataFrame(bars_1h, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
        df_1h['ema200'] = ta.ema(df_1h['close'], length=200)
        trend_1h_up = df_1h.iloc[-1]['close'] > df_1h.iloc[-1]['ema200']
        
        bars_15m = fetch_cached_ohlcv(symbol, timeframe='15m', limit=250)
        df_15m = pd.DataFrame(bars_15m, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
        df_15m['ema200'] = ta.ema(df_15m['close'], length=200)
        
        # حساب الـ ATR على فريم الـ 15 دقيقة (عشان يكون أهدى وأدق للستوب لوز)
        df_15m['atr'] = ta.atr(df_15m['high'], df_15m['low'], df_15m['close'], length=14)
        current_atr = df_15m.iloc[-1]['atr']
        
        trend_15m_up = df_15m.iloc[-1]['close'] > df_15m.iloc[-1]['ema200']
        
        bars_5m = fetch_cached_ohlcv(symbol, timeframe='5m', limit=100)
        df_5m = pd.DataFrame(bars_5m, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
        df_5m['vol_sma'] = ta.sma(df_5m['volume'], length=20)
        
        if "Pro" in current_mode:
            trend_up = trend_1h_up and trend_15m_up
            trend_down = (not trend_1h_up) and (not trend_15m_up)
        else:
            trend_up = trend_15m_up
            trend_down = not trend_15m_up

        df_5m[['bb_lower', 'bb_mid', 'bb_upper']] = ta.bbands(df_5m['close'], length=20).iloc[:, :3]
        kc = ta.kc(df_5m['high'], df_5m['low'], df_5m['close'], length=20, scalar=1.5)
        df_5m['kc_lower'] = kc.iloc[:, 0]
        df_5m['kc_upper'] = kc.iloc[:, 2]
        df_5m['sqz_on'] = (df_5m['bb_lower'] > df_5m['kc_lower']) & (df_5m['bb_upper'] < df_5m['kc_upper'])
        df_5m['sqz_off'] = (df_5m['bb_lower'] < df_5m['kc_lower']) & (df_5m['bb_upper'] > df_5m['kc_upper'])
        df_5m['sqz_fired'] = df_5m['sqz_on'].shift(1) & df_5m['sqz_off']
        
        df_5m['fvg_bull'] = (df_5m['low'] > df_5m['high'].shift(2)) & (df_5m['close'].shift(1) > df_5m['open'].shift(1))
        df_5m['fvg_bear'] = (df_5m['high'] < df_5m['low'].shift(2)) & (df_5m['close'].shift(1) < df_5m['open'].shift(1))
        
        last_5m = df_5m.iloc[-1]
        price = last_5m['close']
        high_volume = last_5m['volume'] > last_5m['vol_sma']

        d_1h = "🟢" if trend_1h_up else "🔴"
        d_15m = "🟢" if trend_15m_up else "🔴"
        d_vol = "🔥" if high_volume else "❄️"
        
        debug_info = f"1H:{d_1h} | 15m:{d_15m} | Vol:{d_vol} | ATR: {current_atr:.4f}"

        sqz_signal = "⏳ WAIT"
        if trend_up and last_5m['sqz_fired'] and high_volume: sqz_signal = "🟢 BUY"
        elif trend_down and last_5m['sqz_fired'] and high_volume: sqz_signal = "🔴 SELL"
            
        brk_signal = "⏳ WAIT"
        if trend_up and last_5m['fvg_bull'] and high_volume: brk_signal = "🟢 BUY"
        elif trend_down and last_5m['fvg_bear'] and high_volume: brk_signal = "🔴 SELL"
            
        return price, sqz_signal, brk_signal, debug_info, current_atr
    except Exception as e:
        return None, "Error", "Error", "Error", 0

col1, col2, col3 = st.columns([1, 1, 1.2])

with col1:
    st.header("💥 Breakout")
with col2:
    st.header("🗜️ Squeeze")
with col3:
    st.header("💼 Smart Portfolio")

for sym in symbols:
    result = analyze_crypto(sym, trading_mode)
    if result[0] is None:
        continue
    price, sqz_signal, brk_signal, debug_info, current_atr = result
        
    mode_label = "🎯 Pro" if "Pro" in trading_mode else "🔥 Action"
    clean_sym = sym.replace(':USDT','')
    
    active_trades_count = len([t for t in portfolio if t.get('status', 'active') == 'active'])
    
    on_cooldown = False
    if sym in cooldowns:
        elapsed = datetime.now() - cooldowns[sym]
        if elapsed < timedelta(minutes=COOLDOWN_MINUTES):
            on_cooldown = True
            rem_mins = COOLDOWN_MINUTES - int(elapsed.total_seconds() / 60)
            debug_info += f" | ⏳ Resting: {rem_mins}m"
    
    if on_cooldown:
        if "BUY" in brk_signal or "SELL" in brk_signal: brk_signal = "⏸️ BLOCKED (Cooldown)"
        if "BUY" in sqz_signal or "SELL" in sqz_signal: sqz_signal = "⏸️ BLOCKED (Cooldown)"
    elif active_trades_count >= max_open_trades and not any(t['symbol'] == sym and t.get('status') == 'active' for t in portfolio):
        if "BUY" in brk_signal or "SELL" in brk_signal: brk_signal = "⏸️ BLOCKED (Max Trades)"
        if "BUY" in sqz_signal or "SELL" in sqz_signal: sqz_signal = "⏸️ BLOCKED (Max Trades)"
    else:
        if "BUY" in brk_signal or "SELL" in brk_signal:
            add_trade(sym, price, "Breakout/SMC", brk_signal, mode_label, current_atr)
            active_trades_count += 1
            
        if active_trades_count < max_open_trades:
            if "BUY" in sqz_signal or "SELL" in sqz_signal:
                add_trade(sym, price, "Squeeze", sqz_signal, mode_label, current_atr)
                active_trades_count += 1
        else:
            if "BUY" in sqz_signal or "SELL" in sqz_signal:
                sqz_signal = "⏸️ BLOCKED (Max Trades)"

    with col1:
        st.markdown(f"### {clean_sym}")
        st.markdown(f"**💰 Price:** ${price}")
        st.info(f"📊 {debug_info}") 
        st.write(f"**Signal:** {brk_signal}")
        if "BUY" in brk_signal or "SELL" in brk_signal: st.success("🤖 Auto-Running")
        elif "Cooldown" in brk_signal: st.warning("⏳ Cooling Down")
        elif "Max Trades" in brk_signal: st.error("🛑 Blocked (Portfolio Full)")
        st.write("---")

    with col2:
        st.markdown(f"### {clean_sym}")
        st.markdown(f"**💰 Price:** ${price}")
        st.info(f"📊 {debug_info}") 
        st.write(f"**Signal:** {sqz_signal}")
        if "BUY" in sqz_signal or "SELL" in sqz_signal: st.success("🤖 Auto-Running")
        elif "Cooldown" in sqz_signal: st.warning("⏳ Cooling Down")
        elif "Max Trades" in sqz_signal: st.error("🛑 Blocked (Portfolio Full)")
        st.write("---")

with col3:
    if len(portfolio) == 0:
        st.info("No open trades currently. Waiting for signals...")
    else:
        for i, trade in enumerate(portfolio):
            display_price = trade['entry_price'] 
            
            if trade.get('status', 'active') == 'active':
                try:
                    ticker = exchange.fetch_ticker(trade['symbol'])
                    current_price = ticker['last']
                    
                    if not trade.get('tp1_executed', False):
                        if "BUY" in trade['direction'] and current_price >= trade['tp1']:
                            trade['tp1_executed'] = True
                            trade['sl'] = trade['entry_price']  
                            trade['sl_moved'] = True
                            trade['realized_pnl'] = 0.5 * (((trade['tp1'] - trade['entry_price'])/trade['entry_price'])*100)
                        elif "SELL" in trade['direction'] and current_price <= trade['tp1']:
                            trade['tp1_executed'] = True
                            trade['sl'] = trade['entry_price']
                            trade['sl_moved'] = True
                            trade['realized_pnl'] = 0.5 * (((trade['entry_price'] - trade['tp1'])/trade['entry_price'])*100)
                    
                    if "BUY" in trade['direction']:
                        if current_price >= trade['tp2']:
                            trade['status'] = 'hit_tp2'
                            trade['exit_price'] = trade['tp2'] 
                            cooldowns[trade['symbol']] = datetime.now()
                            st.rerun() 
                        elif current_price <= trade['sl']:
                            trade['status'] = 'hit_sl'
                            trade['exit_price'] = trade['sl']  
                            cooldowns[trade['symbol']] = datetime.now()
                            st.rerun()
                    else:
                        if current_price <= trade['tp2']:
                            trade['status'] = 'hit_tp2'
                            trade['exit_price'] = trade['tp2']
                            cooldowns[trade['symbol']] = datetime.now()
                            st.rerun()
                        elif current_price >= trade['sl']:
                            trade['status'] = 'hit_sl'
                            trade['exit_price'] = trade['sl']
                            cooldowns[trade['symbol']] = datetime.now()
                            st.rerun()
                            
                    display_price = current_price if trade['status'] == 'active' else trade['exit_price']
                except:
                    display_price = trade['entry_price']
            else:
                display_price = trade['exit_price']
                
            if trade['status'] == 'active':
                if "BUY" in trade['direction']:
                    unrealized_pnl = ((display_price - trade['entry_price']) / trade['entry_price']) * 100
                else: 
                    unrealized_pnl = ((trade['entry_price'] - display_price) / trade['entry_price']) * 100
                
                if trade.get('tp1_executed', False):
                    pnl = trade.get('realized_pnl', 0.0) + (unrealized_pnl * 0.5)
                else:
                    pnl = unrealized_pnl
            else:
                # الحساب النهائي بعد إغلاق الصفقة
                if "BUY" in trade['direction']:
                    final_unrealized = ((trade['exit_price'] - trade['entry_price']) / trade['entry_price']) * 100
                else:
                    final_unrealized = ((trade['entry_price'] - trade['exit_price']) / trade['entry_price']) * 100
                
                if trade.get('tp1_executed', False):
                    pnl = trade.get('realized_pnl', 0.0) + (final_unrealized * 0.5)
                else:
                    pnl = final_unrealized

            pnl_color = "green" if pnl > 0 else "red"
            
            if trade['status'] == 'hit_tp2':
                title_status = f"🎉 Won ({pnl:.2f}%)"
            elif trade['status'] == 'hit_sl':
                title_status = f"🛡️ Break-even ({pnl:.2f}%)" if trade.get('sl_moved', False) else f"🛑 Lost ({pnl:.2f}%)"
            else:
                title_status = f"{pnl:.2f}% (Partial Active)" if trade.get('tp1_executed', False) else f"{pnl:.2f}%"
                
            strat_icon = "💥" if "Breakout" in trade['type'] else "🗜️"
            expander_title = f"{trade['symbol'].replace(':USDT','')} | {trade['mode']} | {strat_icon} | {title_status}"
            
            with st.expander(expander_title, expanded=False):
                st.write(f"**Mode:** {trade['mode']}")
                st.write(f"**Strategy:** {trade['type']}")
                st.write(f"**Direction:** {trade['direction']}")
                st.write(f"**Entry Price:** ${trade['entry_price']}")
                
                # حساب نسبة الستوب لوز الديناميكية عشان تشوفيها بعينك
                dyn_sl_pct = abs(trade['entry_price'] - trade['sl']) / trade['entry_price'] * 100
                
                if trade['status'] == 'active':
                    st.markdown(f"**Live Price:** ${display_price}")
                else:
                    st.markdown(f"**Exit Price:** ${display_price}")
                    
                st.markdown(f"**Total PnL:** <span style='color:{pnl_color}; font-size:18px;'><b>{pnl:.2f}%</b></span>", unsafe_allow_html=True)
                
                if trade.get('tp1_executed', False):
                    st.success("✨ **Partial TP 1 Executed!** (50% profit secured in cash)")

                if trade['status'] == 'hit_tp2':
                    st.success("🎉 **Status: Hit Target 2 (Full Win)**")
                elif trade['status'] == 'hit_sl':
                    if trade.get('sl_moved', False):
                        st.warning("🛡️ **Status: Closed at Entry (Secured First Target Profit)**")
                    else:
                        st.error("🛑 **Status: Hit Stop Loss**")
                else:
                    st.info(f"📏 **Dynamic Risk (ATR):** SL is ~{dyn_sl_pct:.2f}% away from entry")
                    st.write(f"🎯 **Target 1:** ${trade['tp1']:.2f}")
                    st.write(f"🚀 **Target 2:** ${trade['tp2']:.2f}")
                    if trade.get('sl_moved', False):
                        st.success(f"✅ Trade Secured! (Remaining SL = Entry: ${trade['sl']:.2f})")
                    else:
                        st.warning(f"🛑 **Stop Loss:** ${trade['sl']:.2f}")
                    
                if st.button("❌ Remove Trade", key=f"close_{i}"):
                    close_trade(i)
                    st.rerun()
