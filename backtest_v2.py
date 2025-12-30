import yfinance as yf
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
import nifty_utils

def calculate_rsi(series, period=14):
    delta = series.diff()
    gain = (delta.where(delta > 0, 0)).rolling(window=period).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=period).mean()
    rs = gain / loss
    return 100 - (100 / (1 + rs))

def calculate_chop(df, period=14):
    # True Range
    h = df['High']
    l = df['Low']
    c = df['Close']
    pc = c.shift(1)
    
    tr1 = h - l
    tr2 = (h - pc).abs()
    tr3 = (l - pc).abs()
    tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
    
    # ATR Sum
    atr_sum = tr.rolling(window=period).sum()
    
    # Range (Max High - Min Low)
    max_h = h.rolling(window=period).max()
    min_l = l.rolling(window=period).min()
    range_hl = max_h - min_l
    
    # Chop
    # 100 * LOG10( SUM(ATR) / ( MaxHigh - MinLow ) ) / LOG10( n )
    # using np.log10
    
    # Avoid div by zero
    range_hl = range_hl.replace(0, 0.0001)
    
    x = atr_sum / range_hl
    # Log10(x)
    log_x = np.log10(x)
    log_n = np.log10(period)
    
    chop = 100 * (log_x / log_n)
    return chop

def run_simulation():
    print("⏳ Downloading REAL Market Data (Last 45 Days)...")
    
    # Use a solid subset of stocks for speed/relevance
    # Mixing some known runners + standard midcaps
    tickers = [
        "IGL.NS", "MCX.NS", "BSE.NS", "CDSL.NS", "KPITTECH.NS", 
        "IDFCFIRSTB.NS", "POLYCAB.NS", "KEI.NS", "LODHA.NS", "PHOENIXLTD.NS",
        "SUZLON.NS", "ZOMATO.NS", "TATAELXSI.NS", "PERSISTENT.NS", "SCI.NS"
    ]
    # Add some from fallback if needed, but this list is good for verification
    
    start_date = (datetime.now() - timedelta(days=50)).strftime('%Y-%m-%d')
    data = yf.download(tickers, start=start_date, progress=False, group_by='ticker')
    
    # Simulation Window: Last 30 days
    sim_dates = data.index[-30:]
    
    print(f"✅ Data Loaded. Testing Logic from {sim_dates[0].date()} to {sim_dates[-1].date()}")
    print("\n🔍 SIGNAL LOG (Compare with Chart/MoneyControl):")
    print(f"{'DATE':<12} | {'STOCK':<10} | {'PRICE':<8} | {'RSI':<4} | {'CHOP':<4} | {'RESULT'}")
    print("-" * 65)
    
    trades = []
    
    for date in sim_dates:
        idx = data.index.get_loc(date)
        date_str = date.strftime('%Y-%m-%d')
        
        for ticker in tickers:
            try:
                df = data[ticker]
                # Slices
                this_close = df['Close'].iloc[idx]
                prev_close = df['Close'].iloc[idx-1]
                
                # Calculate Indicators on the fly (efficient enough for backtest)
                # Ideally pre-calc, but loop is fine here
                
                # We need series up to this point strictly? 
                # Actually we can pre-calc whole series and just lookup
                pass
            except:
                continue
                
    # PRE-CALCULATION APPROACH (Faster)
    # We will iterate tickers mainly
    
    timeline_events = []
    
    for ticker in tickers:
        try:
            df = data[ticker].copy()
            if df.empty: continue
            
            # Indicators
            df['RSI'] = calculate_rsi(df['Close'])
            df['CHOP'] = calculate_chop(df)
            df['MA20_Vol'] = df['Volume'].rolling(20).mean()
            
            # Signals
            for i in range(len(df)):
                date = df.index[i]
                if date not in sim_dates: continue
                
                rsi = df['RSI'].iloc[i]
                chop = df['CHOP'].iloc[i]
                close = df['Close'].iloc[i]
                vol = df['Volume'].iloc[i]
                ma_vol = df['MA20_Vol'].iloc[i]
                
                score = 0
                if 55 <= rsi <= 70: score += 4
                elif 50 <= rsi < 55: score += 2
                
                if chop < 50: score += 3
                if vol > ma_vol: score += 1
                
                if score >= 8:
                    # Check 5-day Forward Return
                    try:
                        future_close = df['Close'].iloc[i+5]
                        pnl = ((future_close - close)/close)*100
                        res = f"{pnl:+.1f}% (5d)"
                    except:
                        res = "Running..."
                        
                    timeline_events.append({
                        "Date": date,
                        "Stock": ticker.replace(".NS",""),
                        "Price": close,
                        "RSI": rsi,
                        "CHOP": chop,
                        "Result": res
                    })
        except Exception as e:
            # print(e)
            pass
            
    # Sort by date
    timeline_events.sort(key=lambda x: x['Date'])
    
    for t in timeline_events:
        print(f"{t['Date'].strftime('%Y-%m-%d'):<12} | {t['Stock']:<10} | {t['Price']:<8.1f} | {t['RSI']:<4.0f} | {t['CHOP']:<4.0f} | {t['Result']}")

if __name__ == "__main__":
    run_simulation()
