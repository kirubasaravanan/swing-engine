import yfinance as yf
import pandas as pd
import pandas_ta as ta
import numpy as np
from datetime import timedelta, datetime
import nifty_utils

def run_backtest():
    print("⏳ Starting 30-Day Backtest Simulation...")
    
    # 1. SETUP UNIVERSE
    # fast fallback list for speed & reliability
    tickers = nifty_utils.FALLBACK_MIDCAP + nifty_utils.FALLBACK_SMALLCAP
    # LIMIT for speed in this demo run
    tickers = list(set(tickers))[:80] 
    print(f"   Univers: {len(tickers)} stocks")

    # 2. FETCH HISTORY (60 days to allow indicator warmup)
    start_date = (datetime.now() - timedelta(days=60)).strftime('%Y-%m-%d')
    print(f"   Fetching data from {start_date}...")
    
    data = yf.download(tickers, start=start_date, progress=False, group_by='ticker')
    
    # 3. BACKTEST LOOP
    # We want to simulate the last 30 days
    simulation_days = 30
    dates = data.index[-simulation_days:]
    
    portfolio = [] # Active trades
    closed_trades = []
    capital = 50000
    capital_history = []
    
    # Allocation per trade (Max 3 trades)
    MAX_TRADES = 3
    ALLOC_PER_TRADE = capital / MAX_TRADES

    print("\n📅 Simulating Trading Days:")
    
    for i, current_date in enumerate(dates):
        # Data slice up to this date
        # We need to look at 'Yesterday's Close' to decide 'Today's Entry' usually, 
        # or use Closing prices of current day for signal to buy (Swing)
        
        # Current index in the full dataframe
        # We need index in full df to get previous values for indicators
        idx = data.index.get_loc(current_date)
        
        date_str = current_date.strftime('%Y-%m-%d')
        # print(f"   [{date_str}] Processing...")

        # --- A. CHECK EXITS ---
        active_symbols = [t['Symbol'] for t in portfolio]
        for trade in portfolio[:]:
            try:
                # get price for this stock today
                stock_data = data[trade['Symbol']]
                curr_close = stock_data['Close'].iloc[idx]
                curr_rsi = ta.rsi(stock_data['Close'], length=14).iloc[idx]
                
                # CHOP calc (needs 14 days)
                # handle if missing
                try:
                    high = stock_data['High']
                    low = stock_data['Low']
                    close = stock_data['Close']
                    chop_series = ta.chop(high, low, close, length=14)
                    curr_chop = chop_series.iloc[idx]
                except:
                    curr_chop = 50 # neutral fallback
                
                # LOGIC: 
                # 1. SL Hit (-3%)
                # 2. RSI < 45 (Momentum Lost)
                # 3. CHOP > 60 (Market chop)
                
                pnl = (curr_close - trade['Entry']) / trade['Entry']
                
                exit_reason = ""
                if curr_close < trade['Stop']:
                    exit_reason = "SL Hit"
                elif curr_rsi < 45:
                    exit_reason = "Momentum Lost (RSI<45)"
                elif curr_chop > 60:
                    exit_reason = "Chop > 60"
                # Target? Let's verify trailing, but hard target +15%
                elif pnl > 0.15:
                    exit_reason = "Target Play (+15%)"
                    
                if exit_reason:
                    portfolio.remove(trade)
                    realized_pnl = (curr_close - trade['Entry']) * trade['Qty']
                    closed_trades.append({
                        "EntryDate": trade['EntryDate'],
                        "ExitDate": date_str,
                        "Symbol": trade['Symbol'],
                        "Entry": trade['Entry'],
                        "Exit": curr_close,
                        "PnL_Pct": pnl * 100,
                        "Reason": exit_reason
                    })
                    # Free up capital? (Simplified: usually not adding back logic here, valid for simple PnL sum)
            except Exception as e:
                pass # data missing for stock today
                
        # --- B. SCAN FOR ENTRIES ---
        # Only if slots open
        if len(portfolio) < MAX_TRADES:
            candidates = []
            
            for ticker in tickers:
                if ticker in active_symbols: continue
                
                try:
                    df = data[ticker]
                    # Indics
                    close = df['Close'].iloc[idx]
                    prev_close = df['Close'].iloc[idx-1]
                    
                    # Need RSI & CHOP
                    rsis = ta.rsi(df['Close'], length=14)
                    this_rsi = rsis.iloc[idx]
                    
                    # CHOP
                    chops = ta.chop(df['High'], df['Low'], df['Close'], length=14)
                    this_chop = chops.iloc[idx]
                    
                    # Vol
                    vol_ma = df['Volume'].rolling(20).mean()
                    this_vol = df['Volume'].iloc[idx]
                    avg_vol = vol_ma.iloc[idx]
                    
                    # --- TQS LOGIC ---
                    score = 0
                    # RSI Sweet Spot
                    if 55 <= this_rsi <= 70: score += 4
                    elif 50 <= this_rsi < 55: score += 2
                    
                    # Trend Strength
                    if this_chop < 50: score += 3
                    
                    # Volume
                    if this_vol > avg_vol: score += 1
                    
                    # Price Action
                    if close > prev_close: score += 1
                    
                    # Filter: Score >= 8 (Strict)
                    if score >= 8:
                        candidates.append({
                            "Symbol": ticker,
                            "TQS": score,
                            "Price": close,
                            "RSI": this_rsi
                        })
                except Exception:
                    continue
            
            # Sort and Pick
            candidates.sort(key=lambda x: x['TQS'], reverse=True)
            
            # Fill slots
            slots_needed = MAX_TRADES - len(portfolio)
            for buy in candidates[:slots_needed]:
                qty = int(ALLOC_PER_TRADE / buy['Price'])
                if qty < 1: qty = 1
                
                portfolio.append({
                    "Symbol": buy['Symbol'],
                    "Entry": buy['Price'],
                    "EntryDate": date_str,
                    "Qty": qty,
                    "Stop": buy['Price'] * 0.97 # 3% SL
                })
                # print(f"   [BUY] {buy['Symbol']} @ {buy['Price']:.1f} (TQS {buy['TQS']})")

    # --- 4. REPORTING ---
    print("\n" + "="*40)
    print("📊 30-DAY BACKTEST RESULT")
    print("="*40)
    
    df_res = pd.DataFrame(closed_trades)
    if not df_res.empty:
        wins = len(df_res[df_res['PnL_Pct'] > 0])
        total = len(df_res)
        win_rate = (wins/total) * 100
        avg_pnl = df_res['PnL_Pct'].mean()
        
        print(f"Total Trades: {total}")
        print(f"Win Rate:     {win_rate:.1f}%")
        print(f"Avg PnL:      {avg_pnl:.2f}%")
        print("\n📜 Trade Log:")
        print(df_res[['EntryDate','ExitDate','Symbol','PnL_Pct','Reason']].to_string(index=False))
    else:
        print("No trades triggered (Rules might be too strict or data missing).")

    print("\nCurrently Open:")
    for p in portfolio:
        # Calc floating
        try:
            curr = data[p['Symbol']]['Close'].iloc[-1]
            float_pnl = ((curr - p['Entry'])/p['Entry'])*100
            print(f"- {p['Symbol']}: {float_pnl:.1f}% (Entry {p['EntryDate']})")
        except:
            print(f"- {p['Symbol']}")

if __name__ == "__main__":
    run_backtest()
