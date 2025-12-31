import sys
import os
import pandas as pd
import datetime

# MOCK STREAMLIT
class MockSession(dict):
    def __getattr__(self, key): return self.get(key)
    def __setattr__(self, key, val): self[key] = val

import streamlit as st
st.session_state = MockSession()
st.session_state.market_cache = {}

# Import Project Modules
sys.path.append(os.getcwd())
import engine
import market_data

def debug_run():
    print("Starting Debug Run for Exit Manager...")
    
    # 1. Setup Engine
    eng = engine.SwingEngine()
    # Force universe to just these 3 for speed
    eng.universe = ["IFCI.NS", "DMART.NS", "NAVINFLUOR.NS"] 
    
    print(f"Universe: {eng.universe}")
    
    # 2. Fetch Data (Triggers market_data.incremental_fetch)
    print("\nCalling fetch_data()...")
    data_map = eng.fetch_data()
    
    d1_map = data_map.get('1d', {})
    h1_map = data_map.get('1h', {})
    
    print(f"\nData Loaded: {len(d1_map)} Daily DFs, {len(h1_map)} Hourly DFs")
    
    # 3. Inspect Data for IFCI
    target = "IFCI.NS"
    if target in h1_map:
        df = h1_map[target]
        print(f"\nInspecting {target} (Hourly):")
        print(f"   Shape: {df.shape}")
        if not df.empty:
            print("   Last 3 Rows:")
            print(df.tail(3)[['Close', 'Volume']])
            last_dt = df.index[-1]
            print(f"   Last Timestamp: {last_dt}")
            
            # Check against today
            now = pd.Timestamp.now()
            print(f"   Now: {now}")
    else:
        print(f"XXX {target} NOT FOUND in Hourly Map!")

    # 4. Run Check Exits
    print("\nRunning check_exits()...")
    pos_df = pd.DataFrame([
        {'Symbol': 'IFCI', 'Entry': 53.28, 'Date': '2024-12-01'},
        {'Symbol': 'DMART', 'Entry': 3783.70, 'Date': '2024-12-01'},
        {'Symbol': 'NAVINFLUOR', 'Entry': 5890.00, 'Date': '2024-12-01'}
    ])
    
    exits = eng.check_exits(pos_df)
    print("\nExit Analysis Result:")
    for e in exits:
        print(e)

if __name__ == "__main__":
    debug_run()
