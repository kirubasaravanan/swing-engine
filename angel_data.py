import os
import json
import requests
import pandas as pd
from datetime import datetime, timedelta
from angel_connect import AngelOneManager

INSTRUMENT_URL = "https://margincalculator.angelbroking.com/OpenAPI_File/files/OpenAPIScripMaster.json"
INSTRUMENT_FILE = "angel_instruments.json"

class AngelDataManager:
    def __init__(self):
        self.manager = AngelOneManager()
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
                # Fallback to existing if available
                if not os.path.exists(INSTRUMENT_FILE): return

        # Load into memory (Naive Load)
        # Optimized: Only load NSE Equity to save RAM
        print("⚡ Loading Instrument Map...")
        try:
            with open(INSTRUMENT_FILE, "r") as f:
                data = json.load(f)
                
            for item in data:
                if item.get('exch_seg') == 'NSE' and '-EQ' in item.get('symbol'):
                    sym = item['symbol'] # e.g. SBIN-EQ
                    tok = item['token']
                    self.symbol_map[sym] = tok
                    self.token_map[tok] = sym
                    
                    # Also map without suffix for easier lookup
                    clean_sym = sym.replace('-EQ', '')
                    self.symbol_map[clean_sym] = tok
                    
            print(f"✅ Loaded {len(self.symbol_map)} NSE Equity Symbols")
            
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
            
            res = self.manager.smart_api.getCandleData(params)
            
            # HANDLE TOKEN EXPIRY (Auto-Retry)
            if not res['status'] and (res['errorcode'] == 'AG8001' or 'Invalid Token' in res['message']):
                print(f"⚠️ Token Expired for {symbol}. Re-authenticating...")
                success, msg = self.manager.login()
                if success:
                    # Retry Fetch
                    res = self.manager.smart_api.getCandleData(params)
                else:
                    print(f"❌ Re-login failed: {msg}")
                    return pd.DataFrame()

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
