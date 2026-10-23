import ccxt
import time
import pandas as pd
import pandas_ta as ta

# 1. إعدادات الاتصال بالمنصة (OKX Testnet/Live)
exchange = ccxt.okx({
    'apiKey': "41e8e6d1-3d2d-4861-b0df-61ccdb79e34b"
    'secret': "1FC2FDF62E1F188458144B7700759BC3" 
    'password':  "Ahmedengy2010@"
    'enableRateLimit': True,
})

# 2. إعدادات الاستراتيجية
SYMBOLS = ['BTC/USDT', 'ETH/USDT', 'BNB/USDT', 'SOL/USDT']
TIMEFRAME_TREND = '4h'   # فريم الاتجاه العام
TIMEFRAME_ENTRY = '5m'   # فريم التنفيذ
RISK_REWARD_1 = 3        # TP1 = 1:3
RISK_REWARD_2 = 6        # TP2 = 1:6
POLL_INTERVAL = 60       # تحديث كل 60 ثانية

active_positions = {}

# 3. دالة جلب البيانات وتجهيز المؤشرات
def get_data(symbol, timeframe, limit=100):
    bars = exchange.fetch_ohlcv(symbol, timeframe, limit=limit)
    df = pd.DataFrame(bars, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
    df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms')
    return df

# 4. دالة فلتر الاتجاه (4 ساعات)
def get_4h_trend(symbol):
    df = get_data(symbol, TIMEFRAME_TREND)
    df.ta.ema(length=200, append=True) # EMA 200 لتحديد الاتجاه
    current_close = df['close'].iloc[-1]
    ema_200 = df['EMA_200'].iloc[-1]
    
    if current_close > ema_200:
        return 'BULLISH'
    elif current_close < ema_200:
        return 'BEARISH'
    return 'NEUTRAL'

# 5. دالة قنص الصفقات (5 دقائق) - FVG & Squeeze Breakout
def check_entry_signals(symbol, trend):
    df = get_data(symbol, TIMEFRAME_ENTRY)
    
    # حساب مؤشر Squeeze Momentum
    # إعدادات البولينجر وقناة كيلتنر الافتراضية
    df.ta.squeeze(append=True)
    # أسماء الأعمدة الناتجة تختلف حسب الإصدار، عادة SQZ_20_2.0_20_1.5
    sqz_col = [col for col in df.columns if 'SQZ' in col and 'ON' not in col][0] 
    sqz_on = [col for col in df.columns if 'SQZ_ON' in col][0]
    
    last_candle = df.iloc[-2] # الشمعة المغلقة السابقة
    prev_candle = df.iloc[-3]
    
    signal = None
    strategy = None
    entry_price = df['close'].iloc[-1]
    stop_loss = 0
    
    # 1. استراتيجية FVG (الفجوة السعرية)
    # Bullish FVG: Low of candle 3 > High of candle 1
    bullish_fvg = df['low'].iloc[-2] > df['high'].iloc[-4]
    # Bearish FVG: High of candle 3 < Low of candle 1
    bearish_fvg = df['high'].iloc[-2] < df['low'].iloc[-4]
    
    if trend == 'BULLISH' and bullish_fvg:
        signal = 'LONG'
        strategy = 'SMC FVG'
        stop_loss = df['low'].iloc[-4] # الستوب تحت الشمعة الأولى المكونة للفجوة
        
    elif trend == 'BEARISH' and bearish_fvg:
        signal = 'SHORT'
        strategy = 'SMC FVG'
        stop_loss = df['high'].iloc[-4] # الستوب فوق الشمعة الأولى للفجوة
        
    # 2. استراتيجية Squeeze Breakout (الانفجار السعري)
    # الانفجار يحدث عندما يتغير Squeeze من ON إلى OFF مع زخم قوي
    squeeze_fired = (df[sqz_on].iloc[-3] == 1) and (df[sqz_on].iloc[-2] == 0)
    momentum_up = df[sqz_col].iloc[-2] > 0 and df[sqz_col].iloc[-2] > df[sqz_col].iloc[-3]
    momentum_down = df[sqz_col].iloc[-2] < 0 and df[sqz_col].iloc[-2] < df[sqz_col].iloc[-3]
    
    if not signal and squeeze_fired:
        if trend == 'BULLISH' and momentum_up:
            signal = 'LONG'
            strategy = 'Squeeze Breakout'
            stop_loss = df['low'].iloc[-2] - (df['high'].iloc[-2] - df['low'].iloc[-2]) * 0.5 # ستوب لوس ضيق
            
        elif trend == 'BEARISH' and momentum_down:
            signal = 'SHORT'
            strategy = 'Squeeze Breakout'
            stop_loss = df['high'].iloc[-2] + (df['high'].iloc[-2] - df['low'].iloc[-2]) * 0.5

    # حساب الأهداف (Risk/Reward 1:3 و 1:6)
    if signal:
        risk = abs(entry_price - stop_loss)
        if risk == 0: return None
        
        if signal == 'LONG':
            tp1 = entry_price + (risk * RISK_REWARD_1)
            tp2 = entry_price + (risk * RISK_REWARD_2)
        else:
            tp1 = entry_price - (risk * RISK_REWARD_1)
            tp2 = entry_price - (risk * RISK_REWARD_2)
            
        return {
            'symbol': symbol, 'type': strategy, 'direction': signal,
            'entry': entry_price, 'sl': stop_loss, 'tp1': tp1, 'tp2': tp2,
            'status': 'Active', 'secured': False
        }
    return None

# 6. المحرك الرئيسي (إدارة الصفقات والمراقبة اللحظية)
def main_loop():
    print("🐋 تطبيق التداول المؤسسي (SMC & Squeeze Momentum) - (4H & 5m) بدأت المراقبة...")
    
    while True:
        try:
            # 1. البحث عن فرص جديدة
            for symbol in SYMBOLS:
                if symbol not in active_positions:
                    trend_4h = get_4h_trend(symbol)
                    trade = check_entry_signals(symbol, trend_4h)
                    
                    if trade:
                        active_positions[symbol] = trade
                        print(f"\n[NEW TRADE] {symbol} | Type: {trade['type']} | 🟢 {trade['direction']}")
                        print(f"Entry: {trade['entry']:.2f} | TP1: {trade['tp1']:.2f} | TP2: {trade['tp2']:.2f} | SL: {trade['sl']:.2f}")

            # 2. إدارة الصفقات المفتوحة (Breakeven & SL/TP Hit)
            symbols_to_remove = []
            for symbol, pos in active_positions.items():
                ticker = exchange.fetch_ticker(symbol)
                current_price = ticker['last']
                
                # حساب الـ PnL الحي
                if pos['direction'] == 'LONG':
                    pnl_pct = ((current_price - pos['entry']) / pos['entry']) * 100
                else:
                    pnl_pct = ((pos['entry'] - current_price) / pos['entry']) * 100
                    
                print(f"{symbol} | PnL: {pnl_pct:+.2f}% | SL: {pos['sl']:.2f} | Status: {'🛡️ Secured' if pos['secured'] else 'Active'}")

                # خوارزمية الخروج وإدارة المخاطر
                if pos['direction'] == 'LONG':
                    if current_price >= pos['tp2']:
                        print(f"🎯 {symbol} TP2 HIT! Full Profit Secured.")
                        symbols_to_remove.append(symbol)
                    elif current_price >= pos['tp1'] and not pos['secured']:
                        print(f"🛡️ {symbol} TP1 HIT! Moving SL to Breakeven.")
                        pos['sl'] = pos['entry'] # نقل الستوب لوس للدخول
                        pos['secured'] = True
                    elif current_price <= pos['sl']:
                        print(f"🛑 {symbol} SL HIT! Trade Closed.")
                        symbols_to_remove.append(symbol)
                        
                elif pos['direction'] == 'SHORT':
                    if current_price <= pos['tp2']:
                        print(f"🎯 {symbol} TP2 HIT! Full Profit Secured.")
                        symbols_to_remove.append(symbol)
                    elif current_price <= pos['tp1'] and not pos['secured']:
                        print(f"🛡️ {symbol} TP1 HIT! Moving SL to Breakeven.")
                        pos['sl'] = pos['entry']
                        pos['secured'] = True
                    elif current_price >= pos['sl']:
                        print(f"🛑 {symbol} SL HIT! Trade Closed.")
                        symbols_to_remove.append(symbol)

            # تنظيف الصفقات المغلقة
            for sym in symbols_to_remove:
                del active_positions[sym]

            print("-" * 50)
            time.sleep(POLL_INTERVAL) # الانتظار 60 ثانية (لا تغيري هذا الرقم)

        except Exception as e:
            print(f"⚠️ خطأ في الاتصال: {e}")
            time.sleep(10)

if __name__ == '__main__':
    main_loop()
