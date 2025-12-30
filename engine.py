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

from nifty_utils import get_combined_universe

class SwingEngine:
    def __init__(self):
        # Auto-load Midcap/Smallcap Universe
        self.universe = get_combined_universe()
    
    def set_universe(self, tickers):
        if tickers:
            self.universe = [t if ".NS" in t else f"{t}.NS" for t in tickers]

    def fetch_data(self, period="6mo"):
        """Fetch Batch Data"""
        if not self.universe: return {}
        
        print(f"Fetching data for {len(self.universe)} stocks...")
        try:
            # Download batch
            data = yf.download(
                self.universe, 
                period=period, 
                interval="1d", 
                group_by='ticker', 
                progress=False,
                threads=True
            )
            return data
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

    def calculate_tqs(self, row, prev_row=None):
        """
        0-10 Score based on Technicals.
        prev_row: Optional previous day row for trend comparison.
        """
        score = 0
        
        # Guard against NaNs
        try:
            # --- TREND (3 Max) ---
            if row['Close'] > row['EMA_20']: score += 1
            if row['EMA_20'] > row['EMA_50']: score += 1
            if row['Close'] > row['EMA_200']: score += 1
            
            # --- MOMENTUM (4 Max) ---
            rsi = row['RSI']
            
            # 1. RSI Regime
            if 55 <= rsi <= 70:
                score += 2 # SWEET SPOT
            elif 50 <= rsi < 55:
                score += 1 # Warming Up
            elif rsi > 70:
                score += 0 # Overheated
            elif rsi < 50:
                 score -= 1 # Penalty
                 
            # 2. MACD Check
            if row['MACD'] > row['Signal']: score += 1
            
            # 3. Rising RSI
            if prev_row is not None and 'RSI' in prev_row and rsi > prev_row['RSI']:
                 score += 1
            
            # --- STRUCTURE (3 Max) ---
            # 1. Chop Index
            chop = row.get('CHOP', 50)
            if pd.isna(chop): chop = 50
            
            if chop < 50: 
                score += 2
            elif chop < 60:
                score += 1
            else:
                score -= 1
                
            # 2. Volume Pulse (Handle Zero Div risk via safe check)
            vol = row.get('Volume', 0)
            vol_sma = row.get('Vol_SMA', 0)
            if vol > vol_sma and vol_sma > 0: score += 1
            
        except Exception:
            return 0 # Fail safe default
        
        # Cap at 10, Min at 0
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
        Generates detailed metrics for the 'Deep Dive' view.
        Returns dict with: Probability, Break Level, Target, Risk, etc.
        """
        try:
            # 1. Fetch Data (Need enough for 5D High + EMA20 + Indicators)
            df = yf.download(symbol, period="3mo", interval="1d", progress=False)
            if df.empty: return None
            
            # Flatten
            if isinstance(df.columns, pd.MultiIndex):
                 df.columns = df.columns.get_level_values(0)
            df.columns = [str(c) for c in df.columns]
            
            # Indicators
            df = self.calculate_indicators(df)
            if df is None: return None
            
            row = df.iloc[-1]
            tqs = self.calculate_tqs(row, df.iloc[-2])
            
            # 2. Logic - User Specific
            # Break Level = 5D High (Rolling Max of High over 5, shifted by 1 or inclusive?)
            # Usually breakout is > Max(High, 5). 
            # If current price > this, triggered. We just return the level.
            high_5d = df['High'].rolling(window=5).max().iloc[-1]
            
            # SL = EMA20 * 0.96 (4% risk as per request example)
            # OR standard EMA20 if user prefers. Using 4% relative to EMA20 as "Safe Stop"
            ema20 = row['EMA_20']
            sl_safe = ema20 * 0.96
            
            curr_price = row['Close']
            
            # If current price is way above EMA20, risk is high.
            # Entry assumption: TODAY's Close (or recent).
            risk = curr_price - sl_safe
            if risk < 0: risk = curr_price * 0.04 # Fallback if price < EMA20 (downtrend)
            
            # Target 2R
            target = curr_price + (risk * 2)
            
            # Probability
            # TQS 10 = 82%, TQS 9 = 78%, TQS < 9 = 72% (Base)
            prob = 72
            if tqs >= 10: prob = 82
            elif tqs == 9: prob = 78
            
            # EV
            # Win = 8% * Prob/100
            # Loss = 4% * (1-Prob/100)
            win_pct = (target - curr_price) / curr_price
            loss_pct = (curr_price - sl_safe) / curr_price
            ev = (win_pct * (prob/100)) - (loss_pct * ((100-prob)/100))
            
            return {
                "Symbol": symbol,
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
            # print(f"Deep Dive Error: {e}")
            return None

    def check_exits(self, positions_df):
        """
        Check existing positions for Exit Signals.
        positions_df: DataFrame with ['Symbol', 'Entry']
        """
        raw_data = self.fetch_data() # Re-fetch or pass cached data in real app (simplified here)
        if raw_data is None or raw_data.empty: return [] # Handle gracefully
        
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
                
            exits.append({
                'Symbol': row['Symbol'],
                'Current': round(curr_price, 2),
                'PnL %': round(pnl_pct, 1),
                'Action': action,
                'Reason': reason,
                'RSI': round(curr['RSI'], 1),
                'EMA9': round(curr['EMA_9'], 1)
            })
            
        return exits

    def scan(self):
        """Main Scan Loop"""
        raw_data = self.fetch_data()
        results = []
        
        if raw_data is None or raw_data.empty: return []
        
        if raw_data is None or raw_data.empty: return []
        
        tickers = self.universe
        
        # Check column levels
        # Debug showed: Batch -> names=['Ticker', 'Price'] (Ticker is Level 0)
        # Single -> names=['Price', 'Ticker'] (Ticker is Level 1)
        
        ticker_level = 0
        if raw_data.columns.names and 'Ticker' in raw_data.columns.names:
            try:
                ticker_level = raw_data.columns.names.index('Ticker')
            except: pass
        elif raw_data.columns.names and 'Symbol' in raw_data.columns.names:
             try:
                ticker_level = raw_data.columns.names.index('Symbol')
             except: pass
             
        # Fallback heuristic if names are missing
        if getattr(raw_data.columns, 'nlevels', 1) > 1:
            # If level 0 has OHLC, then Ticker is likely Level 1
            if 'Close' in raw_data.columns.get_level_values(0):
                 ticker_level = 1

        for ticker in tickers:
            try:
                df_tick = None
                
                try:
                    # Robust Selection
                    if isinstance(raw_data.columns, pd.MultiIndex):
                         df_tick = raw_data.xs(ticker, axis=1, level=ticker_level).copy()
                    else:
                         # Flat DF (rare for batch)
                         if len(tickers) == 1: df_tick = raw_data.copy()
                except KeyError:
                    continue 

                if df_tick is None or df_tick.empty: continue
                
                # Check if we have Price columns
                if 'Close' not in df_tick.columns: continue

                # Clean NaN rows
                df_tick.dropna(subset=['Close'], inplace=True)
                if len(df_tick) < 50: continue

                # Calc Indicators
                df_calc = self.calculate_indicators(df_tick)
                if df_calc is None: continue
                
                curr = df_calc.iloc[-1]
                prev = df_calc.iloc[-2]
                
                # Score
                tqs = self.calculate_tqs(curr, prev)
                
                # Classify
                tag, intended_entry = self.classify_trade(curr, tqs)
                
                # Confidence Band
                conf = "LOW"
                if tqs >= 9: conf = "EXTREME"
                elif tqs >= 7: conf = "HIGH"
                elif tqs >= 5: conf = "MEDIUM"
                
                # Dynamic Stop
                if "ROCKET" in tag or "MOMENTUM" in tag:
                    stop_lvl = curr['EMA_20']
                else:
                    stop_lvl = curr['EMA_50']

                if tag != "WAIT":
                    results.append({
                        "Symbol": ticker.replace(".NS", ""),
                        "Price": round(curr['Close'], 2),
                        "TQS": tqs,
                        "Confidence": conf,
                        "Type": tag,
                        "Entry": round(intended_entry, 2) if intended_entry > 0 else "Market",
                        "Stop": round(stop_lvl, 2), 
                        "Change": round(((curr['Close'] - prev['Close'])/prev['Close'])*100, 2),
                        "RSI": round(curr['RSI'], 1),
                        "CHOP": round(curr.get('CHOP', 50), 1)
                    })
                    
            except Exception as e:
                # print(f"Error {ticker}: {e}")
                continue
                
        # Sort by TQS
        results.sort(key=lambda x: x['TQS'], reverse=True)
        return results
