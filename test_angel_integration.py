import sys
from unittest.mock import MagicMock

# Mock Streamlit
sys.modules['streamlit'] = MagicMock()
import streamlit as st
class SessionState(dict):
    def __getattr__(self, key): return self.get(key)
    def __setattr__(self, key, value): self[key] = value

st.session_state = SessionState()

import market_data
import os

def test_integration():
    symbol = "RELIANCE.NS"
    print(f"Testing Fetch for {symbol} via market_data...")
    
    # 1. Clear Cache to force fetch
    if 'market_cache' in st.session_state:
        del st.session_state['market_cache']
    
    cache_path = market_data.get_cache_path(symbol, "1d")
    if os.path.exists(cache_path):
        os.remove(cache_path)
        print("Deleted existing cache.")
    
    # 2. Run Fetch
    try:
        df = market_data.incremental_fetch(symbol, interval="1d")
        print("Fetch Complete.")
        print(df.tail())
        
        if not df.empty:
            print("✅ Data Returned Successfully")
            # Verify latest date is recent
            last_date = df.index[-1]
            print(f"Last Date: {last_date}")
        else:
            print("❌ Data is Empty")
            
    except Exception as e:
        print(f"❌ Integration Error: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    with open("test_integration.log", "w", encoding="utf-8") as f:
        f.write("Starting Integration Test...\n")
        f.flush()
        
        # Redirect stdout/stderr to file for this block
        sys.stdout = f
        sys.stderr = f
        
        try:
            test_integration()
        except Exception as e:
            f.write(f"CRITICAL ERROR: {e}\n")
        finally:
            f.flush()
