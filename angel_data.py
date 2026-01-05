import os
import json
import requests
import pandas as pd
from datetime import datetime, timedelta
from angel_connect import AngelOneManager

INSTRUMENT_URL = "https://margincalculator.angelbroking.com/OpenAPI_File/files/OpenAPIScripMaster.json"
INSTRUMENT_FILE = "angel_instruments.json"

import time

class AngelDataManager:
    def __init__(self):
        # 1. Try to Reuse Existing Session from Streamlit (if available)
        try:
             import streamlit as st
             if hasattr(st, 'session_state') and 'angel_client' in st.session_state:
                 self.manager = st.session_state['angel_client']
                 print("✅ AngelDataManager: Reusing Active Session from App.")
             else:
                 raise Exception("No Session Found")
        except:
             # 2. Fresh Login (For Bot / First Run)
             print("🔄 AngelDataManager: Initiating Fresh Login...")
             self.manager = AngelOneManager()
             success, msg = self.manager.login()
             if not success:
                 print(f"❌ AngelDataManager Login Failed: {msg}")
             else:
                 print("✅ AngelDataManager: Login Success.")

        self.symbol_map = {} # {"SBIN-EQ": "3045"}
        self.token_map = {}  # {"3045": "SBIN-EQ"}
        self._load_instruments()

    def _load_instruments(self):
        """Download and cache instrument master."""
        refresh_needed = False
        if not os.path.exists(INSTRUMENT_FILE):
            refresh_needed = True
        else:
            # Refresh if older than 24 hours
            mod_time = datetime.fromtimestamp(os.path.getmtime(INSTRUMENT_FILE))
            if datetime.now() - mod_time > timedelta(hours=24):
                refresh_needed = True
        
        if refresh_needed:
            print("⬇ Downloading Angel One Instrument Dump...")
            try:
                r = requests.get(INSTRUMENT_URL)
                with open(INSTRUMENT_FILE, "wb") as f:
                    f.write(r.content)
            except Exception as e:
                print(f"❌ Failed to download instruments: {e}")
                
        # Validate File Size (Avoid empty file crashes)
        if os.path.exists(INSTRUMENT_FILE) and os.path.getsize(INSTRUMENT_FILE) < 1024:
             print("⚠️ Instrument File too small. Re-downloading...")
             try:
                r = requests.get(INSTRUMENT_URL)
                with open(INSTRUMENT_FILE, "wb") as f: f.write(r.content)
             except: pass

        # Load into memory (Naive Load)
        print("⚡ Loading Instrument Map (Heavy Operation)...")
        try:
            with open(INSTRUMENT_FILE, "r") as f:
                data = json.load(f)
                
            count = 0
            for item in data:
                # Optimized: Only store NSE Equity
                if item.get('exch_seg') == 'NSE' and '-EQ' in item.get('symbol'):
                    sym = item['symbol']
                    tok = item['token']
                    self.symbol_map[sym] = tok
                    self.token_map[tok] = sym
                    
                    # Clean map
                    clean_sym = sym.replace('-EQ', '')
                    self.symbol_map[clean_sym] = tok
                    count += 1
            
            # Explicit Memory Cleanup
            del data
            import gc
            gc.collect()
                    
            print(f"✅ Loaded {count} NSE Equity Symbols")
            
        except Exception as e:
            print(f"❌ Error parsing instruments: {e}")

    def get_token(self, symbol):
        """Standardize symbol (RELIANCE or RELIANCE-EQ) -> Token"""
        symbol = symbol.replace('.NS', '').upper()
        # Try direct match or clean match (handled in load)
        return self.symbol_map.get(symbol)

    def fetch_hist_data(self, symbol, interval="ONE_DAY", days=60):
        """
        Fetch OHLCV data.
        interval: 'ONE_MINUTE', 'FIFTEEN_MINUTE', 'ONE_HOUR', 'ONE_DAY'
        """
        # 1. Login if needed
        if not self.manager.auth_token:
            success, msg = self.manager.login()
            if not success:
                print(f"Login Failed in Data Fetch: {msg}")
                return pd.DataFrame()

        # 2. Resolve Token
        token = self.get_token(symbol)
        if not token:
            print(f"❌ Token not found for {symbol}")
            return pd.DataFrame()
            
        # 3. Time params
        to_date = datetime.now()
        from_date = to_date - timedelta(days=days)
        
        # Angel format: 'YYYY-MM-DD HH:MM'
        fmt = "%Y-%m-%d %H:%M"
        
        try:
            params = {
                "exchange": "NSE",
                "symboltoken": token,
                "interval": interval,
                "fromdate": from_date.strftime(fmt),
                "todate": to_date.strftime(fmt)
            }
            
            # RETRY LOOP (Rate Limit & Token Handling)
            max_retries = 3
            for attempt in range(max_retries):
                res = self.manager.smart_api.getCandleData(params)
                
                # Check Success
                if res['status'] and res['data']:
                    break # Success!
                    
                # Handle Token Error
                if not res['status'] and (res['errorcode'] == 'AG8001' or 'Invalid Token' in res['message']):
                    print(f"⚠️ Token Expired for {symbol}. Re-authenticating...")
                    success, msg = self.manager.login()
                    if success: continue # Retry loop
                    else: return pd.DataFrame()
                
                # Handle Rate Limit / AB1004
                if not res['status'] and res['errorcode'] == 'AB1004':
                    wait_time = (attempt + 1) * 2 # 2s, 4s, 6s
                    print(f"⚠️ Rate Limit (AB1004) for {symbol}. Retrying in {wait_time}s...")
                    time.sleep(wait_time)
                    continue
                
                # Other Errors -> Break
                break
            
            # THROTTLE (Prevent bursting)
            time.sleep(0.4) 

            if res['status'] and res['data']:
                # Parse Data
                # Response format: [timestamp, open, high, low, close, volume]
                cols = ['Date', 'Open', 'High', 'Low', 'Close', 'Volume']
                df = pd.DataFrame(res['data'], columns=cols)
                df['Date'] = pd.to_datetime(df['Date'])
                df.set_index('Date', inplace=True)
                
                # Cleanup Types
                df = df.astype(float)
                return df
            else:
                print(f"⚠️ No Data for {symbol}: {res['message']}")
                return pd.DataFrame()
                
        except Exception as e:
            print(f"❌ Fetch Error {symbol}: {e}")
            return pd.DataFrame()

    def fetch_market_data_batch(self, symbols, mode="FULL"):
        """
        Fetch Real-Time Data for multiple symbols (Max 50 per batch safe).
        mode: "LTP", "OHLC", "FULL"
        Returns DataFrame with Symbol index.
        """
        # 1. Map Symbols to Tokens
        token_map = {} # {token: symbol}
        tokens = []
        for s in symbols:
            t = self.get_token(s)
            if t:
                tokens.append(t)
                token_map[t] = s
                
        # 2. Batching (API limit usually 50)
        BATCH_SIZE = 50
        all_results = []
        
        for i in range(0, len(tokens), BATCH_SIZE):
            batch = tokens[i:i+BATCH_SIZE]
            
            try:
                # Mode "FULL" gives LTP, Open, High, Low, Close, Volume, LastTradeQty, etc.
                res = self.manager.smart_api.getMarketData(mode, exchangeTokens={"NSE": batch})
                
                # RETRY LOGIC (Auto-Heal)
                if not res['status'] and (res['errorcode'] == 'AG8001' or 'Invalid Token' in res['message']):
                    print("⚠️ Token Expired during Batch Fetch. Re-authenticating...")
                    success, msg = self.manager.login()
                    if success:
                        # Retry
                        res = self.manager.smart_api.getMarketData(mode, exchangeTokens={"NSE": batch})
                    else:
                        print(f"❌ Re-login failed: {msg}")
                
                if res['status'] and res['data']:
                    all_results.extend(res['data']) # List of dicts
                    
                time.sleep(0.25) # Throttle (4 req/sec max)
                    
            except Exception as e:
                print(f"⚠️ Market Data Batch Failed: {e}")
                
        # 3. Process Result
        if not all_results: return pd.DataFrame()
        
        # Format: {'tradingSymbol': '...', 'symbolToken': '...', 'ltp': ...}
        data = []
        for item in all_results:
            tok = item.get('symbolToken')
            sym = token_map.get(tok)
            if not sym: continue
            
            # Extract Keys based on mode
            row = {'Symbol': sym}
            if 'ltp' in item: row['LTP'] = float(item['ltp'])
            if 'percentChange' in item: row['Change'] = float(item['percentChange'])
            if 'netChange' in item: row['PtsChange'] = float(item['netChange'])
            if 'volume' in item: row['Volume'] = int(item['volume'])
            # Full OHLCa
            if 'open' in item: row['Open'] = float(item['open'])
            if 'high' in item: row['High'] = float(item['high'])
            if 'low' in item: row['Low'] = float(item['low'])
            if 'close' in item: row['Close'] = float(item['close']) # Previous Close often
            
            data.append(row)
            
        return pd.DataFrame(data).set_index('Symbol')

if __name__ == "__main__":
    with open("angel_data_debug.log", "w", encoding="utf-8") as f:
        f.write("Starting Data Test...\n")
        f.flush()
        try:
            f.write("Initializing Manager...\n")
            f.flush()
            test = AngelDataManager()
            f.write("Manager Initialized. Fetching RELIANCE...\n")
            f.flush()
            df = test.fetch_hist_data("RELIANCE", interval="ONE_DAY", days=5)
            f.write("Fetch Result:\n")
            f.write(str(df) + "\n")
            f.flush()
        except Exception as e:
            f.write(f"CRITICAL DATA ERROR: {e}\n")
            f.flush()
