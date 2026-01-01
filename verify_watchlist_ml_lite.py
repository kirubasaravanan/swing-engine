
import streamlit as st
if 'engine_version' not in st.session_state: st.session_state['engine_version'] = "1.2"

from engine import SwingEngine
import json

def verify_lite():
    print("[INFO] Starting Watchlist 2.0 Verification (LITE MODE)...")
    
    engine = SwingEngine()
    print("[OK] Engine Initialized")
    
    # OVERRIDE UNIVERSE for Speed
    engine.universe = ['RELIANCE.NS', 'TCS.NS', 'INFY.NS', 'HDFCBANK.NS', 'ICICIBANK.NS']
    print(f"[INFO] Universe Overridden to {len(engine.universe)} stocks for rapid testing.")
    
    # Check Discord Init
    if hasattr(engine, 'discord') and engine.discord:
        print("[PASS] Discord Bot Initialized (Module Loaded)")
        
        # Verify Dual Channels
        bot_url = engine.discord.url_bot
        stocks_url = engine.discord.url_stocks
        
        if bot_url and "1456270113803075605" in bot_url:
            print("[PASS] Bot Alert Webhook Configured Correctly")
        else:
            print(f"[FAIL] Bot Webhook Missing or Wrong (Got: {str(bot_url)[:10]}...)")
            
        if stocks_url and "1456271069416784020" in stocks_url:
            print("[PASS] Stock Alert Webhook Configured Correctly")
        else:
            print(f"[FAIL] Stock Webhook Missing or Wrong (Got: {str(stocks_url)[:10]}...)")
            
    else:
        print("[FAIL] Discord Bot attribute missing or None")
    
    print("[INFO] Running update_watchlist()...")
    # This should be instant if cache exists, or fast fetch for just 5
    updated_list = engine.update_watchlist()
    
    print(f"[OK] Watchlist Updated. Count: {len(updated_list)}")
    
    if not updated_list:
        print("[WARN] No candidates found in this tiny universe.")
        return

    sample = updated_list[0]
    print("\n[INFO] Inspecting Sample Record:")
    print(json.dumps(sample, indent=4))
    
    required = ['status', 'max_tqs', 'exit_reason']
    missing = [f for f in required if f not in sample]
    
    if missing:
        print(f"[FAIL] Missing fields {missing}")
    else:
        print("[PASS] All ML Fields Present")

if __name__ == "__main__":
    verify_lite()
