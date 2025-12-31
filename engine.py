import yfinance as yf
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
        """Fetch Multi-Timeframe Batch Data (15m, 1h, 1d)"""
        if not self.universe: return {}
        
        print(f"Fetching Multi-TF data for {len(self.universe)} stocks...")
        tickers = self.universe
        
        data_map = {}
        
        try:
            # 1. Daily (3mo) for Trend & Weekly Gain
            print(".. Downloading Daily Data")
            d_1d = yf.download(tickers, period="3mo", interval="1d", group_by='ticker', progress=False, threads=True)
            data_map['1d'] = d_1d
            
            # 2. Hourly (1mo) for TQS Core (RSI, Vol, Chop)
            print(".. Downloading Hourly Data")
            d_1h = yf.download(tickers, period="1mo", interval="1h", group_by='ticker', progress=False, threads=True)
            data_map['1h'] = d_1h
            
            # 3. 15-Min (5d) for Entry Timing
            print(".. Downloading 15m Data")
            d_15m = yf.download(tickers, period="5d", interval="15m", group_by='ticker', progress=False, threads=True)
            data_map['15m'] = d_15m
            
            return data_map
        except Exception as e:
            print(f"Fetch Error: {e}")
            return {}

    def calculate_indicators(self, df):
        """Add Technicals (EMA, RSI, MACD)"""
        if df.empty: return None
        
        # Ensure single level column if series
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
            
            # Use log10 from numpy
            # Avoid division by zero
            df['CHOP'] = 100 * np.log10(sum_tr_14 / range_14) / np.log10(14)
            
            return df
        except Exception as e:
            # print(f"Indicator Error: {e}")
            return None

    def get_live_price(self, symbol):
        """Fetches the latest close price for a single symbol."""
        try:
            df = yf.download(symbol, period="1d", interval="1m", progress=False)
            if not df.empty:
                # Handle MultiIndex if present
                if isinstance(df.columns, pd.MultiIndex):
                     return df['Close'].iloc[-1].values[0]
                return df['Close'].iloc[-1]
        except:
            return None
        return None

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
        data_map = self.fetch_data() # Returns dict {'15m':..., '1h':...}
        if not data_map: return []
        
        # Use 1H data for Exits (Dynamic) or 1D for Trend?
        # Let's use 1H for granular exits (RSI > 75 etc)
        raw_data = data_map.get('1h')
        if raw_data is None or raw_data.empty: return []
        
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
            sym = row['Symbol'] + ".NS"
            entry = float(row['Entry'])
            
            df_tick = get_df_tick(raw_data, sym)
            
            if df_tick is None or df_tick.empty:
                 # Fallback: Try fetch single
                 try: 
                     df_tick = yf.download(sym, period="60d", progress=False)
                 except: continue
            
            if df_tick is None or df_tick.empty: continue

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

    def get_weekly_rankings(self, d_1d):
        """
        Compute top weekly gainers from Daily Data.
        Returns: Dict {Symbol: {'Rank': 1, 'Percent': 15.2, 'Category': 'MIDCAP'}}
        """
        rankings = []
        
        # Helper to categorize
        def get_cat(sym):
            s = sym if ".NS" in sym else sym + ".NS"
            return self.category_map.get(s, "Total Market")

        # Dynamic Ticker Level Detection
        tickers = []
        ticker_level = 0
        
        if isinstance(d_1d.columns, pd.MultiIndex):
            # Try to find which level looks like a Ticker (string, contains .NS or is upper)
            # Usually Level 0 is Ticker for group_by='ticker'
            # But yfinance changed recently to (Price, Ticker) sometimes.
            
            l0 = d_1d.columns.get_level_values(0)
            l1 = d_1d.columns.get_level_values(1) if d_1d.columns.nlevels > 1 else []
            
            if len(l0) > 0 and ".NS" in str(l0[0]):
                ticker_level = 0
                tickers = l0.unique()
            elif len(l1) > 0 and ".NS" in str(l1[0]):
                ticker_level = 1
                tickers = l1.unique()
            elif len(l0) > 0 and str(l0[0]).isupper() and "CLOSE" not in str(l0[0]).upper():
                 # Maybe tickers without .NS
                 ticker_level = 0
                 tickers = l0.unique()
            else:
                 # Fallback: Assume Level 0 if not Price
                 ticker_level = 0
                 tickers = l0.unique()
        else:
             return {}

        for ticker in tickers:
            try:
                # Robust extract
                df = d_1d.xs(ticker, axis=1, level=ticker_level)
                if len(df) < 6: continue
                
                curr = df['Close'].iloc[-1]
                week_ago = df['Close'].iloc[-6] 
                pct = ((curr - week_ago) / week_ago) * 100
                
                rankings.append({
                    'Symbol': ticker,
                    'Percent': pct,
                    'Category': get_cat(ticker)
                })
            except: continue
            
        # Sort
        rankings.sort(key=lambda x: x['Percent'], reverse=True)
        
        # Convert to Map for O(1) Lookup
        # We only care about Top 20 for highlighting
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
        """Main Scan Loop (Multi-Timeframe)"""
        if progress_callback: progress_callback(0.05) # 5% - Reading Config
        
        # 1. Fetch ALL Data
        data_map = self.fetch_data()
        if not data_map: return []
        
        d_15m = data_map.get('15m')
        d_1h = data_map.get('1h')
        d_1d = data_map.get('1d')
        
        # --- PRE-CALCULATE WEEKLY RANKINGS ---
        weekly_map = self.get_weekly_rankings(d_1d)
        
        results = []
        tickers = self.universe
        total_tickers = len(tickers)
        
        # Helper to extract single stock DF from batch
        def get_df(batch_data, tic):
            try:
                if isinstance(batch_data.columns, pd.MultiIndex):
                    # Level 0 is usually Ticker if group_by='ticker'
                    return batch_data.xs(tic, axis=1, level=0).copy()
                return None
            except: return None

        for i, ticker in enumerate(tickers):
            if progress_callback:
                try:
                    p = 0.10 + (0.90 * (i + 1) / total_tickers)
                    progress_callback(p)
                except: pass

            try:
                # Extract 3 Timeframes
                df_15 = get_df(d_15m, ticker)
                df_60 = get_df(d_1h, ticker)
                df_day = get_df(d_1d, ticker)
                
                if df_15 is None or df_60 is None or df_day is None: continue
                if df_day.empty or len(df_day) < 20: continue 
                
                df_15.dropna(subset=['Close'], inplace=True)
                df_60.dropna(subset=['Close'], inplace=True)
                df_day.dropna(subset=['Close'], inplace=True)
                
                # Indicators
                df_15 = self.calculate_indicators(df_15)
                df_60 = self.calculate_indicators(df_60)
                df_day = self.calculate_indicators(df_day) 
                
                if df_15 is None or df_60 is None or df_day is None: continue

                # Weekly Data (Look up from map for consistency)
                clean_ticker = ticker.replace(".NS", "")
                w_data = weekly_map.get(clean_ticker, {'Rank': 999, 'Percent': 0.0, 'Category': ''})
                weekly_gain = w_data['Percent']
                
                # Score
                tqs = self.calculate_tqs_multi_tf(df_15, df_60, df_day)
                rev_tqs = self.calculate_reverse_tqs(df_60.iloc[-1], df_day)
                
                # Tag Logic
                curr_price = df_day['Close'].iloc[-1]
                row_1h = df_60.iloc[-1]
                prev_1h = df_60.iloc[-2]
                
                tag = "WAIT"
                conf = "LOW"
                
                # Tagging Priority: Weekly Rocket > TQS Score > Reverse TQS (Sell)
                if w_data['Rank'] <= 5 and tqs >= 7:
                    tag = f"🔥 #{w_data['Rank']} W.GAINER ({w_data['Category']})"
                    conf = "EXTREME"
                elif tqs >= 8:
                    tag = "BUY SIGNAL"
                    if weekly_gain > 5: tag = f"ROCKET ({w_data['Category']})"
                    conf = "HIGH"
                    if tqs >= 9: conf = "EXTREME"
                elif rev_tqs >= 8:
                    tag = "SELL SIGNAL"
                    conf = "HIGH"
                elif tqs >= 5:
                    tag = "WATCH"
                    conf = "MEDIUM"

                # Dynamic Stop
                stop_lvl = row_1h.get('EMA_20', curr_price * 0.95)

                if tag != "WAIT":
                    results.append({
                        "Symbol": clean_ticker,
                        "Price": round(curr_price, 2),
                        "TQS": tqs,
                        "RevTQS": rev_tqs,
                        "Confidence": conf,
                        "Type": tag,
                        "Weekly %": round(weekly_gain, 1),
                        "Category": w_data['Category'],
                        "Entry": "Market",
                        "Stop": round(stop_lvl, 2), 
                        "Change": round(((curr_price - prev_1h['Close'])/prev_1h['Close'])*100, 2),
                        "RSI": round(row_1h.get('RSI', 50), 1)
                    })
                    
            except Exception as e:
                continue
                
        results.sort(key=lambda x: x['TQS'], reverse=True)
        return results
