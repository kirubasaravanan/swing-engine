import pandas as pd
import numpy as np
from engine import SwingEngine
import traceback

def create_poison_data():
    """Generates dataframes guaranteed to break fragile code."""
    datasets = {}
    
    # 1. Zero Volume (Div by Zero risk)
    df_zero = pd.DataFrame({
        'Open': [100]*100, 'High': [105]*100, 'Low': [95]*100, 'Close': [100]*100,
        'Volume': [0]*100
    })
    datasets['Zero Volume'] = df_zero

    # 2. NaNs Everywhere
    df_nan = pd.DataFrame({
        'Open': [np.nan]*100, 'High': [np.nan]*100, 'Low': [np.nan]*100, 'Close': [np.nan]*100,
        'Volume': [np.nan]*100
    })
    datasets['All NaNs'] = df_nan
    
    # 3. Short Data (Not enough for RSI-14)
    df_short = pd.DataFrame({
        'Open': [100]*5, 'High': [105]*5, 'Low': [95]*5, 'Close': [100]*5,
        'Volume': [1000]*5
    })
    datasets['Short Data (<14d)'] = df_short

    # 4. Perfect Flatline (RSI Calc Div by Zero risk if delta is 0)
    df_flat = pd.DataFrame({
        'Open': [100]*50, 'High': [100]*50, 'Low': [100]*50, 'Close': [100]*50,
        'Volume': [1000]*50
    })
    datasets['Flatline Price'] = df_flat

    return datasets

def run_stress_test():
    print("🛡️ STARTING ROBUSTNESS STRESS TEST...")
    engine = SwingEngine()
    
    # PHASE 1: SYNTHETIC EDGE CASES
    print("\n[PHASE 1] Synthetic Poison Data Injection")
    print("-" * 50)
    
    poison_pill = create_poison_data()
    failures = 0
    
    for name, df in poison_pill.items():
        print(f"Testing Scenario: {name}...", end=" ")
        try:
            # Inject into calculation logic directly
            # We mock the internal structure expecting 'Ticker' keys usually, 
            # but we can test the calculation methods if we extract them or mock scanning
            
            # Let's use calculate_indicators logic. 
            # engine.scan() does fetching + calc. We want to test calc.
            # We'll rely on engine.calculate_indicators accepting a DF? 
            # Looking at engine.py, calculate_indicators takes (df).
            
            # Need to ensure dates index for CHOP
            df.index = pd.date_range(start='2024-01-01', periods=len(df))
            
            processed = engine.calculate_indicators(df)
            
            # Compute TQS
            score = engine.calculate_tqs(processed)
            
            print("✅ PASSED (Handled Gracefully)")
            
        except Exception as e:
            print(f"❌ CRASHED: {e}")
            # traceback.print_exc()
            failures += 1

    # PHASE 2: FULL UNIVERSE DATA SCAN
    print("\n[PHASE 2] Full Universe Real-Time Scan (150+ Stocks)")
    print("-" * 50)
    print("Fetching ALL data (Please wait)...")
    
    try:
        # Force full scan
        results = engine.scan()
        print(f"✅ Scan Completed Successfully.")
        print(f"   Processed: {len(results)} valid signals returned.")
        
    except Exception as e:
        print(f"❌ REAL DATA CRASH: {e}")
        traceback.print_exc()
        failures += 1

    print("\n" + "="*30)
    if failures == 0:
        print("🎉 RESULT: SYSTEM IS ROBUST. 0 FAILURES.")
    else:
        print(f"⚠️ RESULT: {failures} FAILURES DETECTED.")
    print("="*30)

if __name__ == "__main__":
    run_stress_test()
