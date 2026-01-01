
import streamlit as st
# Mock session state for engine init
if 'engine_version' not in st.session_state: st.session_state['engine_version'] = "1.2"

from engine import SwingEngine
import pandas as pd
import json
import os

def verify():
    print("🧪 Starting Watchlist 2.0 Verification (ML Data Layer)...")
    
    # 1. Initialize Engine
    engine = SwingEngine()
    print("✅ Engine Initialized")
    
    # 2. Run Update Watchlist
    # This will fetch data (cache/live) and update db.json
    print("🔄 Running update_watchlist()...")
    updated_list = engine.update_watchlist()
    
    print(f"✅ Watchlist Updated. Count: {len(updated_list)}")
    
    # 3. Inspect Data Structure
    if not updated_list:
        print("⚠️ Watchlist is empty. Cannot verify fields.")
        return

    sample = updated_list[0]
    print("\n🔍 Inspecting Sample Record:")
    print(json.dumps(sample, indent=4))
    
    # 4. Check Required Fields
    required = ['status', 'max_tqs', 'exit_reason', 'days_tracked']
    missing = [f for f in required if f not in sample]
    
    if missing:
        print(f"❌ FAIL: Missing fields {missing}")
    else:
        print("✅ PASS: All ML Fields Present")
        
    # 5. Check Logic
    actives = [x for x in updated_list if x.get('status') == 'ACTIVE']
    inactives = [x for x in updated_list if x.get('status') == 'INACTIVE']
    
    print(f"\n📊 Logic Check:")
    print(f"   Active: {len(actives)}")
    print(f"   Inactive: {len(inactives)}")
    
    if len(actives) > 50:
        print("❌ FAIL: Active Count > 50")
    else:
        print("✅ PASS: Active Count <= 50")

if __name__ == "__main__":
    verify()
