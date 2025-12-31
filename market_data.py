import os
import pandas as pd
import datetime
try:
    import streamlit as st
except ImportError:
    st = None

# --- CONFIG ---
CACHE_DIR = "cache"
os.makedirs(CACHE_DIR, exist_ok=True)

def get_cache_path(symbol, interval):
    clean_sym = symbol.replace(".NS", "").replace("^", "")
    return os.path.join(CACHE_DIR, f"{clean_sym}_{interval}.parquet")

def incremental_fetch(symbol, interval="1d", period="1y"):
    """
    Fetches data incrementally:
    1. Checks local Parquet cache.
    2. Downloads only NEW data from Yahoo.
    3. Merges and updates cache.
    4. Returns DataFrame.
    """
    
    # 0. Memory Cache (Session State) - Fastest
    mem_key = f"market_{symbol}_{interval}"
    if 'market_cache' not in st.session_state:
        st.session_state.market_cache = {}
        
    if mem_key in st.session_state.market_cache:
        # We could add a TTL here if needed, but for a 15 min session it's fine
        return st.session_state.market_cache[mem_key]

    path = get_cache_path(symbol, interval)
    existing_df = pd.DataFrame()
    start_date = None
    
    # 1. Load Parquet
    if os.path.exists(path):
        try:
            existing_df = pd.read_parquet(path)
            if not existing_df.empty:
                last_dt = existing_df.index[-1]
                # If timezone aware, convert to naive for comparison or keep aware?
                # YF usually returns aware. Let's ensure we handle it.
                if isinstance(last_dt, pd.Timestamp):
                     # FIX: Start from the SAME day to update partial candles (e.g. morning -> EOD)
                     start_date = last_dt.strftime('%Y-%m-%d')
                
                # OPTIMIZATION: If last candle is "Recent Enough" (e.g. today/yesterday depending on time), maybe skip?
                # For now, we trust the incremental fetch to be fast (empty response if up to date).
        except Exception as e:
            print(f"Cache Read Error {symbol}: {e}")
            # FIX: Corrupt file? Delete it to self-heal.
            try: os.remove(path)
            except: pass
            existing_df = pd.DataFrame()

# 2. Fetch from Angel One (Primary)
    try:
        # Initialize Angel Manager only once
        mgr = None
        
        # Streamlit Context
        if st is not None and hasattr(st, 'session_state'):
            if 'angel_mgr' not in st.session_state:
                 from angel_data import AngelDataManager
                 st.session_state.angel_mgr = AngelDataManager()
            mgr = st.session_state.angel_mgr
        else:
            # Headless / Bot Context (Global Fallback)
            # We use a simple global singleton pattern here if needed, 
            # or just instantiate for now (Bot runs once so it is fine)
            from angel_data import AngelDataManager
            # In a real bot, we might want to keep this instance alive across loop iterations.
            # For now, let's instantiate.
            mgr = AngelDataManager()

        # Calculate days needed
        days_to_fetch = 365 # Default period="1y" -> ~365 days
        if period == "1mo": days_to_fetch = 30
        if period == "5y": days_to_fetch = 1500
        
        # If increment, just fetch last 5 days to be safe and cover holidays
        if start_date:
            days_to_fetch = 10 
            
        angel_interval = "ONE_DAY"
        if interval == "1h": angel_interval = "ONE_HOUR"
        if interval == "15m": angel_interval = "FIFTEEN_MINUTE"

        new_data = mgr.fetch_hist_data(symbol, interval=angel_interval, days=days_to_fetch)
        
    except Exception as e:
        print(f"Angel Download Error {symbol}: {e}")
        new_data = pd.DataFrame()

    # 3. Merge Strategies
    if not new_data.empty:
        # Standardize Columns (MultiIndex issues with yfinance recent versions)
        # If 'Adj Close' missing, map 'Close'
        if isinstance(new_data.columns, pd.MultiIndex):
            new_data.columns = new_data.columns.get_level_values(0)
            
        # Clean: Drop rows with all NaNs
        new_data.dropna(how='all', inplace=True)
        
        if existing_df.empty:
            final_df = new_data
        else:
            # Concatenate and Drop Duplicates
            # Ensure index types match
            if existing_df.index.tz is None and new_data.index.tz is not None:
                new_data.index = new_data.index.tz_localize(None)
            elif existing_df.index.tz is not None and new_data.index.tz is None:
                existing_df.index = existing_df.index.tz_localize(None) # Or localize new_data
                
            final_df = pd.concat([existing_df, new_data])
            final_df = final_df[~final_df.index.duplicated(keep='last')]
        
        # Save to Parquet
        try:
            final_df.to_parquet(path)
        except Exception as e:
            print(f"Cache Write Error {symbol}: {e}")
            
    else:
        final_df = existing_df

    # 4. Update Memory Cache
    st.session_state.market_cache[mem_key] = final_df
    
    return final_df

def clear_cache():
    """Utils to clear cache if things break"""
    if 'market_cache' in st.session_state:
        st.session_state.market_cache = {}
    # Could also delete files, but risky.
