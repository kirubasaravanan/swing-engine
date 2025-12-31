import pandas as pd
from engine import SwingEngine
import sheets_db
import time

def run_eod():
    print("Initializing EOD Scan...")
    
    # 1. Init Engine
    engine = SwingEngine()
    print(f"univ: {len(engine.universe)} stocks (Next50 + Mid + Small)")
    
    # 2. Run Scan
    # We can pass a dummy progress callback
    def progress(p):
        print(f"  > Progress: {int(p*100)}%")
        
    results = engine.scan(progress_callback=progress)
    
    # 3. Display Top Results
    print(f"\nScan Complete. Found {len(results)} matches.")
    
    df = pd.DataFrame(results)
    if not df.empty:
        # Show Top 5
        print("\nTop 5 Picks:")
        cols = ['Symbol', 'TQS', 'RevTQS', 'Weekly %', 'Type', 'Price']
        cols = [c for c in cols if c in df.columns]
        print(df[cols].head(5).to_string(index=False))

        # DEBUG: Why 0.0?
        try:
            sample = df.iloc[0]
            sym = sample['Symbol']
            print(f"\nDEBUG DATA for {sym}:")
            # Fetch fresh 1d to see
            import yfinance as yf
            dd = yf.download(f"{sym}.NS", period="10d", interval="1d", progress=False)
            print(dd.tail(7))
            if len(dd) >= 6:
                c = dd['Close'].iloc[-1]
                w = dd['Close'].iloc[-6]
                print(f"Close Now: {c}, Close 5d agg: {w}")
        except: pass
        
        # Check for Weekly Gainers
        gainers = df[df['Weekly %'] > 5]
        if not gainers.empty:
            print(f"\nFound {len(gainers)} Weekly Gainers (>5%)")
    
    # 4. Save to DB
    print("\nSaving to Google Sheet (LatestScan)...")
    sheets_db.save_scan_results(results)
    
    # Also save to PostMarket if distinct?
    # For now, LatestScan is the source of truth as discussed.
    print("Done.")

if __name__ == "__main__":
    run_eod()
