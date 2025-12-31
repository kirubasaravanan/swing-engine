import pandas as pd
import numpy as np
import time

# --- CONSTANTS ---
DEFAULT_TICKERS = [
    "RELIANCE.NS", "HDFCBANK.NS", "INFY.NS", "TCS.NS", "ICICIBANK.NS",
    "TATAMOTORS.NS", "SBIN.NS", "BAJFINANCE.NS", "BHARTIARTL.NS", "ITC.NS",
    "ADANIENT.NS", "KPITTECH.NS", "ZOMATO.NS", "HAL.NS", "TRENT.NS",
    "VBL.NS", "COALINDIA.NS", "ONGC.NS", "NTPC.NS", "POWERGRID.NS"
]

from nifty_utils import get_combined_universe, get_categorized_universe

class SwingEngine:
    def __init__(self):
        # Auto-load Midcap/Smallcap Universe
        univ, cat_map = get_categorized_universe()
        self.universe = univ
        self.category_map = cat_map
    
    def set_universe(self, tickers):
        if tickers:
            self.universe = [t if ".NS" in t else f"{t}.NS" for t in tickers]

    def fetch_data(self):
        """Fetch Multi-Timeframe Batch Data (15m, 1h, 1d) via Market Data Engine"""
        import market_data
        from concurrent.futures import ThreadPoolExecutor, as_completed
        
        if not self.universe: return {}
        
        max_workers = 4
        print(f"Fetching Data for {len(self.universe)} stocks (Parallel {max_workers} Threads)...")
        tickers = self.universe
        
        # Prepare containers (using dict of DF instead of MultiIndex DF for better stability)
        # Note: DOWNSTREAM compatibility -> scan() iterates tickers. 
        # If we return a dict of {ticker: df}, scan logic needs to support it.
        # Currently scan() likely iterates tickers and expects to slice a Batch DF.
        # Let's see...
        # scan() extracts using: if sym in raw_data: df_tick = raw_data[sym]
        # Providing a dict {'1d': {'RELIANCE.NS': DF, ...}} matches that access pattern perfectly!
        
        data_map = {'1d': {}, '1h': {}, '15m': {}}
        
        def fetch_worker(sym):
            try:
                # 3 Calls per ticker? That's heavy (750 calls).
                # Optimization: 
                # 1. Fetch 1D (Trend) - 3mo
                # 2. Fetch 1H (TQS) - 1mo
                # 3. Fetch 15m (Entry) - 5d
                # We thread this to maximize throughput (~3 req/sec limit)
                
                # Note: market_data.incremental_fetch handles cache/angel transparently
                d1 = market_data.incremental_fetch(sym, interval="1d", period="3mo")
                d1h = market_data.incremental_fetch(sym, interval="1h", period="1mo")
                d15 = market_data.incremental_fetch(sym, interval="15m", period="5d")
                return sym, d1, d1h, d15
            except:
                return sym, None, None, None

        # Execute Parallel Fetch (Limit 5 threads to avoid rate limit spam)
        # Angel Limit: 3 requests per second. 
        # With 5 threads doing 3 calls each = 15 calls. Might hit rate limit.
        # Let's stick to 2 threads or add sleep.
        # SmartApi python wrapper handles some retries? No.
        # We'll rely on our AG8001 retry logic + rate limiting.
        
        with ThreadPoolExecutor(max_workers=4) as executor:
            # Submit all
            futures = {executor.submit(fetch_worker, t): t for t in tickers}
            
            for future in as_completed(futures):
                sym, d1, d1h, d15 = future.result()
                if d1 is not None and not d1.empty: data_map['1d'][sym] = d1
                if d1h is not None and not d1h.empty: data_map['1h'][sym] = d1h
                if d15 is not None and not d15.empty: data_map['15m'][sym] = d15

        return data_map

    def calculate_indicators(self, df):
        """Add Technicals (EMA, RSI, MACD)"""
        if df.empty: return None
        
        # Ensure single level column if series
        df = df.copy() # Critial Fix for Data Leaking
        try:
            # EMA
            df['EMA_9'] = df['Close'].ewm(span=9, adjust=False).mean()
            df['EMA_20'] = df['Close'].ewm(span=20, adjust=False).mean()
            df['EMA_50'] = df['Close'].ewm(span=50, adjust=False).mean()
            df['EMA_200'] = df['Close'].ewm(span=200, adjust=False).mean()
            
            # RSI
            delta = df['Close'].diff()
            gain = (delta.where(delta > 0, 0)).rolling(window=14).mean()
            loss = (-delta.where(delta < 0, 0)).rolling(window=14).mean()
            rs = gain / loss
            df['RSI'] = 100 - (100 / (1 + rs))
            
            # MACD
            ema12 = df['Close'].ewm(span=12, adjust=False).mean()
            ema26 = df['Close'].ewm(span=26, adjust=False).mean()
            df['MACD'] = ema12 - ema26
            df['Signal'] = df['MACD'].ewm(span=9, adjust=False).mean()
            
            # ATR (Approx)
            df['TR'] = np.maximum(
                df['High'] - df['Low'],
                np.maximum(
                    abs(df['High'] - df['Close'].shift(1)),
                    abs(df['Low'] - df['Close'].shift(1))
                )
            )
            df['ATR'] = df['TR'].rolling(window=14).mean()
            
            # Volume SMA
            df['Vol_SMA'] = df['Volume'].rolling(window=20).mean()
            
            # Highs
            df['High_20'] = df['High'].rolling(window=20).max()
            
            # --- CHOP INDEX (14) ---
            # 100 * LOG10( SUM(TR, 14) / (MaxHi(14) - MinLo(14)) ) / LOG10(14)
            high_14 = df['High'].rolling(window=14).max()
            low_14 = df['Low'].rolling(window=14).min()
            range_14 = high_14 - low_14
            sum_tr_14 = df['TR'].rolling(window=14).sum()
            
            # Avoid Division by Zero & Invalid Log inputs
            # Replace 0 range with NaN or small epsilon
            range_14 = range_14.replace(0, np.nan) 
            
            ratio = sum_tr_14 / range_14
            df['CHOP'] = 100 * np.log10(ratio) / np.log10(14)
            
            # Fill NaNs (first 14 rows) with 50 (Neutral)
            df['CHOP'] = df['CHOP'].fillna(50)
            
            # Handle Infinite?
            df['CHOP'] = df['CHOP'].replace([np.inf, -np.inf], 50)
            
            return df
        except Exception as e:
            # print(f"Indicator Error: {e}")
            return None

    def get_live_price(self, symbol):
        """Fetches the latest close price for a single symbol via Angel One."""
        try:
             import streamlit as st
             if 'angel_mgr' in st.session_state:
                 mgr = st.session_state.angel_mgr
                 # Fetch 1 day, 1m interval to get latest
                 # Or use specific "LTP" API if available? 
                 # Candle is safer for consistency
                 df = mgr.fetch_hist_data(symbol, interval="ONE_MINUTE", days=2)
                 if df is not None and not df.empty:
                     return df['Close'].iloc[-1]
             return 0.0
        except:
            return 0.0
        return 0.0

    def calculate_tqs_multi_tf(self, df_15m, df_1h, df_1d):
        """
        Calculates TQS based on 3 Timeframes (0-10 Score).
        Factors: Trend (2), RSI (2), Volume (2), Structure (2), Momentum (2)
        """
        score = 0
        try:
            # Get latest rows
            row_15m = df_15m.iloc[-1]
            row_1h = df_1h.iloc[-1]
            row_1d = df_1d.iloc[-1]
            
            # 1. TREND (2 pts): Price > EMA20 on ALL TFs
            # Note: We need to assume indicators are already calculated on these DFs
            trend_score = 0
            if (row_15m['Close'] > row_15m.get('EMA_20', 999999) and 
                row_1h['Close'] > row_1h.get('EMA_20', 999999) and 
                row_1d['Close'] > row_1d.get('EMA_20', 999999)):
                trend_score = 2
            score += trend_score
            
            # 2. RSI (2 pts): 1H RSI in Sweet Spot (55-70)
            rsi = row_1h.get('RSI', 50)
            rsi_score = 0
            if 55 <= rsi <= 70: rsi_score = 2
            elif 50 <= rsi <= 75: rsi_score = 1
            score += rsi_score
            
            # 3. VOLUME (2 pts): 1H Volume > 20MA * 1.2 + Green Candle
            vol = row_1h.get('Volume', 0)
            vol_avg = row_1h.get('Vol_SMA', 99999999)
            vol_score = 1 # Default neutral
            if vol > (vol_avg * 1.2) and row_1h['Close'] > row_1h['Open']:
                vol_score = 2
            score += vol_score
            
            # 4. STRUCTURE (2 pts): 1H CHOP < 50
            chop = row_1h.get('CHOP', 50)
            struct_score = 0
            if chop < 50: struct_score = 2
            elif chop < 55: struct_score = 1
            score += struct_score
            
            # 5. MOMENTUM (2 pts): 1H MACD > Signal + Price > VWAP (Using EMA20 as VWAP proxy here to save fetch)
            # Proxy: Price > EMA20 and MACD bullish
            mom_score = 1
            macd = row_1h.get('MACD', 0)
            sig = row_1h.get('Signal', 0)
            if row_1h['Close'] > row_1h.get('EMA_20', 0) and macd > sig:
                mom_score = 2
            score += mom_score
            
        except Exception:
            return 0
            
        return max(min(score, 10), 0)

    def classify_trade(self, row, tqs):
        """
        Classify: SWING | MOMENTUM | RANGE BREAK | WAIT
        """
        # Default
        tag = "WAIT"
        rec_entry = 0.0
        
        if tqs >= 8:
            # STRONG
            # Check for "Gainer Forecast" (Volume Shock + Breakout)
            vol_shock = row['Volume'] > (row['Vol_SMA'] * 2.0)
            
            if vol_shock and row['Close'] > row['High_20']:
                tag = "ROCKET LAUNCH 🚀" # Explosive Start
                rec_entry = row['Close']
            elif row['Close'] > row['High_20']:
                tag = "RANGE BREAK"
                rec_entry = row['Close'] # Market
            elif row['RSI'] > 60:
                tag = "MOMENTUM SWING"
                rec_entry = row['Close']
            else:
                tag = "SWING BUILD"
                rec_entry = row['EMA_20'] # Limit Idea
        elif tqs >= 5:
            # MID
            if row['Close'] < row['EMA_20'] and row['Close'] > row['EMA_50']:
                tag = "PULLBACK WATCH"
                rec_entry = row['EMA_50']
            else:
                tag = "WATCH"
        
        return tag, rec_entry

    def get_tqs_deep_dive(self, symbol):
        """
        Generates detailed metrics using Multi-TF Data.
        """
        try:
            # 1. Fetch Multi-TF Data (Synchronous for single stock)
            # Need threads=False for single to avoid overhead? Actually yf is fast.
            # Using same fetch logic but for single ticker
            
            # Format ticker
            if ".NS" not in symbol: symbol += ".NS"
            
            d_15m = yf.download(symbol, period="5d", interval="15m", progress=False)
            d_1h = yf.download(symbol, period="1mo", interval="1h", progress=False)
            d_1d = yf.download(symbol, period="3mo", interval="1d", progress=False)
            
            if d_15m.empty or d_1h.empty or d_1d.empty: return None
            
            # Indicators
            d_15m = self.calculate_indicators(d_15m)
            d_1h = self.calculate_indicators(d_1h) # Main logic uses 1H
            d_1d = self.calculate_indicators(d_1d)
            
            if d_1h is None: return None

            # Calculate TQS with new Multi-TF function
            tqs = self.calculate_tqs_multi_tf(d_15m, d_1h, d_1d)
            
            # Get latest rows
            row = d_1h.iloc[-1]
            curr_price = row['Close']
            
            # 2. Key Levels
            # Break Level = 5D High (From Daily)
            high_5d = d_1d['High'].rolling(window=5).max().iloc[-1]
            
            # Stop Loss (Dynamic: EMA20 on 1H for entered momentum)
            ema20 = row.get('EMA_20', curr_price * 0.95)
            sl_safe = ema20
            
            # Risk
            risk = curr_price - sl_safe
            if risk < 0: risk = curr_price * 0.01 # Fallback min risk
            
            # Target 2R
            target = curr_price + (risk * 2)
            
            # Probability (TQS based)
            prob = 72
            if tqs >= 10: prob = 82
            elif tqs == 9: prob = 78
            
            # EV Calculation
            win_pct = (target - curr_price) / curr_price
            loss_pct = (curr_price - sl_safe) / curr_price
            ev = (win_pct * (prob/100)) - (loss_pct * ((100-prob)/100))
            
            return {
                "Symbol": symbol.replace(".NS", ""),
                "Price": curr_price,
                "TQS": tqs,
                "StopLoss": sl_safe,
                "Target": target,
                "Risk": risk,
                "BreakLevel": high_5d,
                "Probability": prob,
                "EV_Pct": ev * 100
            }
        except Exception as e:
            print(f"Deep Dive Error: {e}")
            return None

    def check_exits(self, positions_df):
        """
        Check existing positions for Exit Signals.
        positions_df: DataFrame with ['Symbol', 'Entry']
        """
        # Optimize: Only fetch data for portfolio stocks
        unique_tickers = []
        if 'Symbol' in positions_df.columns:
            raw_syms = positions_df['Symbol'].unique()
            # Ensure proper format (append .NS if missing, or handle both?)
            # The fetcher expects .NS usually for Yahoo
            unique_tickers = [s + ".NS" if ".NS" not in s else s for s in raw_syms]

        # Fetch Limited Data (Instant Sequential Fetch)
        data_map = self.fetch_data(limit_to_tickers=unique_tickers)
        if not data_map: return []
        
        # Use 1H data for Exits (Dynamic) or 1D for Trend?
        # Let's use 1H for granular exits (RSI > 75 etc)
        raw_data = data_map.get('1h')
        if not raw_data: return []
        
        exits = []
        
        # Simpler fetch for portfolio (fetch only what we own if universe is huge?)
        # For now, assuming portfolio is subset of scanned universe or just re-using raw_data
        
        # We need a robust "Get Ticker" helper from raw_data like in scan()
        # reusing logic...
        
        # Quick helper to extract single DF from batch
        def get_df_tick(data, tick):
            # Same extraction logic as scan...
            # simplified for brevity assuming standard batch
            try:
                if isinstance(data.columns, pd.MultiIndex):
                    # Try both levels just in case
                    try: return data.xs(tick, axis=1, level=0).copy()
                    except: return data.xs(tick, axis=1, level=1).copy()
                else:
                    return data.copy()
            except: return None

        for idx, row in positions_df.iterrows():
            raw_sym = row['Symbol']
            # Ensure .NS consistency
            sym = raw_sym + ".NS" if ".NS" not in raw_sym else raw_sym
            clean_sym = raw_sym.replace(".NS", "")
            
            entry = float(row['Entry'])
            
            # Try finding in batch data using both formats
            df_tick = None
            if raw_data is not None:
                # Try Keys: "RELIANCE.NS", "RELIANCE", "REL..."
                if sym in raw_data: df_tick = raw_data[sym]
                elif clean_sym in raw_data: df_tick = raw_data[clean_sym]
                # If raw_data is MultiIndex DataFrame (from batch download)
                elif isinstance(raw_data.columns, pd.MultiIndex):
                     try: df_tick = raw_data.xs(sym, axis=1, level=0)
                     except: 
                        try: df_tick = raw_data.xs(clean_sym, axis=1, level=0)
                        except: pass
            
            # Fallback: Force Download (Angel One)
            if df_tick is None or df_tick.empty:
                 try: 
                     if 'angel_mgr' in st.session_state:
                         mgr = st.session_state.angel_mgr
                         # Fetch 5 days history for fallback
                         df_tick = mgr.fetch_hist_data(sym, interval="ONE_HOUR", days=5)
                 except: continue
            
            if df_tick is None or df_tick.empty: continue
            
            # DEBUG: Trace Data Source
            try:
                # Get scalar close properly to avoid ambiguity
                last_price = df_tick['Close'].iloc[-1]
                if isinstance(last_price, pd.Series): last_price = last_price.iloc[0]
                print(f"Set: {sym} | Source: {'Cache' if sym in raw_data else 'Download'} | Price: {float(last_price)}")
            except Exception as e: print(f"Debug Err: {e}")

            # FLATTEN COLUMNS (Critical Fix)
            # yfinance returns MultiIndex (Price, Ticker) or (Ticker, Price)
            if isinstance(df_tick.columns, pd.MultiIndex):
                # If we can extract by symbol (if symbol is in columns)
                # Check if symbol is in the levels
                found = False
                for level in range(df_tick.columns.nlevels):
                    if sym in df_tick.columns.get_level_values(level):
                        df_tick = df_tick.xs(sym, axis=1, level=level)
                        found = True
                        break
                
                # If not found (maybe just Price levels), just drop levels to get names
                if not found:
                    df_tick.columns = df_tick.columns.get_level_values(0)
            
            # Ensure we have clean string columns
            df_tick.columns = [str(c) for c in df_tick.columns]

            if 'Close' not in df_tick.columns: continue
            
            # Indicators
            df_calc = self.calculate_indicators(df_tick)
            if df_calc is None: continue
            curr = df_calc.iloc[-1]
            
            # EXIT LOGIC
            action = "HOLD"
            reason = ""
            
            curr_price = curr['Close']
            pnl_pct = ((curr_price - entry) / entry) * 100
            
            # Days Held
            days_held = 0
            try:
                entry_date = pd.to_datetime(row['Date'])
                today = pd.Timestamp.now()
                days_held = (today - entry_date).days
            except: pass
            
            # 1. Profit Target (Momentum Fade)
            if curr['RSI'] > 75:
                action = "BOOK PROFIT"
                reason = "RSI Overheated (>75)"
            elif pnl_pct > 15:
                action = "BOOK PARTIAL"
                reason = "Target Hit (>15%)"
                
            # 2. Trailing Stop (Momentum Loss)
            elif curr_price < curr['EMA_9']:
                action = "TRAIL EXIT"
                reason = "Lost Momentum (< EMA9)"
                
            # 3. Hard Stop (Trend Loss)
            elif curr_price < curr['EMA_20']:
                action = "HARD EXIT"
                reason = "Trend Broken (< EMA20)"
                
            # 4. Weakness (Reverse TQS)
            # We can calculate RevTQS here too if we passed daily data
            # For now keeping it simple based on EMA/RSI
                
            exits.append({
                'Symbol': row['Symbol'],
                'Current': round(curr_price, 2),
                'PnL %': round(pnl_pct, 1),
                'Action': action,
                'Reason': reason,
                'Days': days_held,
                'RSI': round(curr['RSI'], 1),
                'EMA9': round(curr['EMA_9'], 1)
            })
            
        return exits

    def calculate_reverse_tqs(self, row, df_daily):
        """
        Calculates Reverse TQS (Weakness/Sell Score 0-10).
        High Score = Strong Sell Signal.
        """
        score = 0
        try:
            # 1. TREND BROKEN (3 pts)
            # Price < EMA20 on Daily (-2) and Hourly (-1)
            ema20 = row.get('EMA_20', 0)
            if row['Close'] < ema20: score += 2
            
            # Daily Trend check (using last row of daily)
            d_row = df_daily.iloc[-1]
            if d_row['Close'] < d_row.get('EMA_20', 0): score += 1
            
            # 2. MOMENTUM FADE (3 pts)
            # RSI < 40 (Oversold/Bearish) or RSI Divergence (simplified)
            rsi = row.get('RSI', 50)
            if rsi < 40: score += 2     # Bearish Regime
            elif rsi < 50: score += 1   # Weak
            
            # MACD Bearish
            if row.get('MACD', 0) < row.get('Signal', 0): score += 1
            
            # 3. VOLUME DISTRIBUTION (2 pts)
            # Red candle with High Vol
            if row['Close'] < row['Open'] and row.get('Volume', 0) > row.get('Vol_SMA', 0):
                score += 2
                
            # 4. STRUCTURE (2 pts)
            # Lower Lows? (Simple proxy: Close < Prev Close)
            if row['Close'] < row.get('Open', 0): score += 2
            
        except: return 0
        return max(min(score, 10), 0)

    def fetch_data(self, limit_to_tickers=None):
        """
        Fetch Multi-Timeframe Data.
        limit_to_tickers: Optional list of specific symbols to fetch (e.g. for Portfolio).
        """
        if not self.universe and not limit_to_tickers: return {}
        
        import market_data
        
        # Determine scope
        tickers = limit_to_tickers if limit_to_tickers else self.universe
        # Ensure unique and formatted (roughly) if needed
        tickers = list(set(tickers))
        
        print(f"⚡ Fetching Data for {len(tickers)} stocks (Sequential + Parquet)...")
        
        results = {'1d': {}, '1h': {}, '15m': {}}
        
        def fetch_ticker_tfs(ticker):
            # Fetch all 3 timeframes for one ticker
            try:
                # 1D: Need large history for trend/weekly (3mo is safe default for fetch, cache handles it)
                d1 = market_data.incremental_fetch(ticker, "1d", "1y") # 1y for robust daily
                
                # 1H: Need 1mo for Chop/RSI
                h1 = market_data.incremental_fetch(ticker, "1h", "1mo")
                
                # 15M: Need 5d for Entry
                m15 = market_data.incremental_fetch(ticker, "15m", "5d")
                
                return ticker, d1, h1, m15
            except:
                return ticker, None, None, None

        # SEQUENTIAL EXECUTION (Fixes Data Leak & Race Conditions)
        for t in tickers:
             tic, d1, h1, m15 = fetch_ticker_tfs(t)
             if d1 is not None and not d1.empty: results['1d'][tic] = d1
             if h1 is not None and not h1.empty: results['1h'][tic] = h1
             if m15 is not None and not m15.empty: results['15m'][tic] = m15

        print(f"⚡ Data Loaded. 1D: {len(results['1d'])} | 1H: {len(results['1h'])} | 15M: {len(results['15m'])}")
        return results

    def get_weekly_rankings(self, d_1d_dict):
        """
        Compute top weekly gainers from Daily Data Dict.
        d_1d_dict: {Symbol: DataFrame}
        """
        rankings = []
        
        def get_cat(sym):
            return self.category_map.get(sym, "Total Market")

        for ticker, df in d_1d_dict.items():
            try:
                if df is None or df.empty or len(df) < 6: continue
                
                # Cleaning: Flatten MultiIndex Columns if present
                if isinstance(df.columns, pd.MultiIndex):
                    # Attempt to simplify columns to Single Level
                    try:
                        # Assuming Level 0 is Ticker or Price?
                        # If we have (Ticker, Price) -> Level 1 is Price
                        # If we have (Price, Ticker) -> Level 0 is Price
                        # Let's try to find 'Close' in strings
                        pass # Rely on xs or get_level_values
                        df.columns = df.columns.get_level_values(0)
                    except: pass
                
                # Fallback: If columns are tuples, map to string
                if not df.empty and isinstance(df.columns[0], tuple):
                     df.columns = [str(c[0]) for c in df.columns]

                # Extract Close
                try:
                    vals = df['Close'].values
                except:
                    # Try finding column that contains "Close"
                    cols = [c for c in df.columns if "Close" in str(c)]
                    if not cols: continue
                    vals = df[cols[0]].values
                
                if vals.ndim > 1: vals = vals[:, 0]
                if len(vals) < 6: continue
                
                curr = float(vals[-1])
                week_ago = float(vals[-6])
                
                if week_ago == 0: continue
                
                pct = ((curr - week_ago) / week_ago) * 100
                
                rankings.append({
                    'Symbol': ticker,
                    'Percent': pct,
                    'Category': get_cat(ticker)
                })
            except Exception: 
                continue
            
        rankings.sort(key=lambda x: x['Percent'], reverse=True)
        
        rank_map = {}
        for i, r in enumerate(rankings):
            clean_sym = r['Symbol'].replace(".NS", "")
            rank_map[clean_sym] = {
                'Rank': i + 1,
                'Percent': r['Percent'],
                'Category': r['Category']
            }
        return rank_map

    def scan(self, progress_callback=None):
        """Main Scan Loop (Optimized for Dictionary Data)"""
        if progress_callback: progress_callback(0.05)
        
        # 1. Fetch ALL Data (Dict of Dicts)
        data_map = self.fetch_data()
        if not data_map: return []
        
        d_1d = data_map.get('1d', {})
        d_1h = data_map.get('1h', {})
        d_15m = data_map.get('15m', {})
        
        # --- PRE-CALCULATE WEEKLY RANKINGS ---
        weekly_map = self.get_weekly_rankings(d_1d)
        
        results = []
        tickers = self.universe
        total_tickers = len(tickers)
        
        for i, ticker in enumerate(tickers):
            if progress_callback and i % 10 == 0:
                try: progress_callback(0.10 + (0.90 * (i + 1) / total_tickers))
                except: pass

            try:
                # Direct Dict Lookup (O(1))
                df_day = d_1d.get(ticker)
                df_60 = d_1h.get(ticker)
                df_15 = d_15m.get(ticker)
                
                if df_day is None or df_60 is None or df_15 is None: continue
                if len(df_day) < 20: continue
                
                # Indicators (Calculated on Single-DF copy - fast)
                # Note: df is passed by reference, but we assign new columns. 
                # This modifies the cached DF in Session State (Good! Computed once).
                if 'EMA_200' not in df_day.columns: df_day = self.calculate_indicators(df_day)
                if 'EMA_50' not in df_60.columns: df_60 = self.calculate_indicators(df_60)
                if 'EMA_20' not in df_15.columns: df_15 = self.calculate_indicators(df_15) # 15m needs less but consistent
                
                if df_day is None or df_60 is None or df_15 is None: continue

                # Weekly Data
                clean_ticker = ticker.replace(".NS", "")
                w_data = weekly_map.get(clean_ticker, {'Rank': 999, 'Percent': 0.0, 'Category': ''})
                
                # Score
                tqs = self.calculate_tqs_multi_tf(df_15, df_60, df_day)
                rev_tqs = self.calculate_reverse_tqs(df_60.iloc[-1], df_day)
                
                # Tag Logic
                curr_price = df_day['Close'].iloc[-1]
                
                tag = "WAIT"
                conf = "LOW"
                
                if w_data['Rank'] <= 10 and tqs >= 7:
                    tag = f"🔥 #{w_data['Rank']} W.GAINER ({w_data['Category']})"
                    conf = "EXTREME"
                elif tqs >= 8:
                    tag = "🚀 ROCKET"
                    conf = "HIGH"
                elif w_data['Percent'] > 5 and tqs >= 6:
                    tag = "💪 STRONG"
                    conf = "HIGH"
                elif rev_tqs >= 7:
                    tag = "⚠️ SELL SIGNAL"
                    conf = "LOW"

                # Safe Extraction Helper
                def get_val(series, default=0.0):
                    try:
                        val = series.iloc[-1]
                        if isinstance(val, pd.Series): val = val.iloc[0]
                        return float(val)
                    except: return float(default)

                # Result Object (Strict JSON Compatibility)
                chop_val = 50.0
                if 'CHOP' in df_day.columns:
                    chop_val = get_val(df_day['CHOP'], 50.0)

                results.append({
                    'Symbol': str(clean_ticker),
                    'Price': float(round(get_val(df_day['Close']), 2)),
                    'Change': float(round(((get_val(df_day['Close']) - get_val(df_day['Open']))/get_val(df_day['Open']) )*100, 2)),
                    'TQS': int(tqs),
                    'RevTQS': int(rev_tqs),
                    'Weekly %': float(round(w_data['Percent'], 2)),
                    'Type': str(tag),
                    'Confidence': str(conf),
                    'RSI': float(round(get_val(df_day['RSI']), 1)),
                    'CHOP': float(round(chop_val, 1)),
                    'Stop': float(round(get_val(df_day['EMA_20']), 2)), 
                    'Entry': float(round(get_val(df_day['Close']), 2))
                })
                
            except Exception as e:
                # print(f"Scan Error {ticker}: {e}")
                continue
                
        # Sort by Ranking (Rocket/Weekly top)
        # Priority: Confidence (EXTREME > HIGH) -> TQS
        results.sort(key=lambda x: (1 if x['Confidence']=='EXTREME' else 0, x['TQS']), reverse=True)
        return results

    def update_watchlist(self):
        """Phase 5: Smart Scalable Watchlist Logic (Top 5 TQS>=8 -> 50 Max)"""
        import sheets_db
        print("🔄 Updating Smart Watchlist...")
        
        # 1. Fetch Data
        data_map = self.fetch_data()
        d_1d = data_map.get('1d', {})
        d_1h = data_map.get('1h', {})
        d_15m = data_map.get('15m', {})
        
        candidates = []
        
        for ticker in self.universe:
            try:
                # Direct Lookup
                df_day = d_1d.get(ticker)
                df_60 = d_1h.get(ticker)
                df_15 = d_15m.get(ticker)
                
                if df_day is None or df_60 is None or df_15 is None: continue
                if len(df_day) < 20: continue
                
                # Indicators (Fast calc on copy)
                if 'EMA_200' not in df_day.columns: df_day = self.calculate_indicators(df_day)
                if 'EMA_50' not in df_60.columns: df_60 = self.calculate_indicators(df_60)
                if 'EMA_20' not in df_15.columns: df_15 = self.calculate_indicators(df_15)
                
                if df_day is None or df_60 is None: continue
                
                # Score
                tqs = self.calculate_tqs_multi_tf(df_15, df_60, df_day)
                
                # Add if TQS >= 8
                if tqs >= 8:
                    curr_price = df_day['Close'].iloc[-1]
                    candidates.append({
                        'Symbol': ticker,
                        'TQS': int(tqs),
                        'Price': float(round(curr_price, 2)),
                        'Date Added': pd.Timestamp.now().strftime("%Y-%m-%d")
                    })
            except Exception as e: continue
            
        print(f"   > Found {len(candidates)} High-Quality Candidates (TQS>=8)")
        
        # 2. Merge with Existing
        current_wl = sheets_db.fetch_watchlist()
        
        # Convert to Dict for easy merge {Symbol: Record}
        # Preference: New scan data updates TQS/Price, preserves Date Added (if exists)
        wl_map = {item['Symbol']: item for item in current_wl}
        
        for cand in candidates:
            if cand['Symbol'] in wl_map:
                # Update TQS/Price, Keep Date
                wl_map[cand['Symbol']]['TQS'] = cand['TQS']
                wl_map[cand['Symbol']]['Price'] = cand['Price']
            else:
                # Add New
                wl_map[cand['Symbol']] = cand
        
        # 3. Trim to Top 50 by TQS
        final_list = list(wl_map.values())
        final_list.sort(key=lambda x: x['TQS'], reverse=True)
        final_list = final_list[:50]
        
        # 4. Save
        sheets_db.save_watchlist(final_list)
        return final_list
