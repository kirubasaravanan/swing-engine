from engine import SwingEngine
from nifty_utils import get_combined_universe

def test():
    print("1. Testing Nifty Index Fetcher...")
    uni = get_combined_universe()
    print(f"   > Got {len(uni)} stocks in universe.")
    if len(uni) > 0:
        print(f"   > Sample: {uni[:5]}")
    
    print("\n2. Initializing Engine...")
    eng = SwingEngine()
    print(f"   > Engine Universe Size: {len(eng.universe)}")
    
    # Run small scan on first 5 to verify yfinance
    if len(eng.universe) > 5:
        print("\n3. Running Test Scan on Top 5 Stocks...")
        eng.universe = eng.universe[:5] # Override for quick test
        results = eng.scan()
        if results:
            print("   > Scan Success!")
            print(f"   > Top Result: {results[0]}")
        else:
            print("   > Scan returned no results (Data fetch issue?)")
    
    print("\nTest Complete.")

if __name__ == "__main__":
    test()
