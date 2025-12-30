import os
import json
import pandas as pd
from datetime import datetime
from engine import SwingEngine
import sheets_db

# --- SETUP CREDENTIALS ---
if "GCP_SERVICE_ACCOUNT" in os.environ:
    with open("service_account.json", "w") as f:
        f.write(os.environ["GCP_SERVICE_ACCOUNT"])

def main():
    print("🤖 Swing Bot Waking Up...")
    engine = SwingEngine()
    
    # 1. FETCH OPEN TRADES
    print("1. Checking Open Positions...")
    open_trades = sheets_db.fetch_portfolio()
    current_count = len(open_trades) if open_trades else 0
    print(f"   > Found {current_count} active trades.")
    
    # 2. CHECK EXITS
    if current_count > 0:
        pos_df = pd.DataFrame(open_trades)
        # Ensure correct types
        pos_df['Entry'] = pd.to_numeric(pos_df['Entry'])
        
        exits = engine.check_exits(pos_df)
        
        for exit_sig in exits:
            # Action required?
            if "EXIT" in exit_sig['Action'] or "BOOK" in exit_sig['Action']:
                print(f"   🚨 EXECUTING EXIT: {exit_sig['Symbol']} ({exit_sig['Reason']})")
                
                # Archive
                trade_record = {
                    "Date": datetime.now().strftime("%Y-%m-%d"),
                    "Symbol": exit_sig['Symbol'],
                    "Entry": 0, # Need to lookup org entry, simplified for now
                    "Exit": exit_sig['Current'],
                    "PnL": exit_sig['PnL %'],
                    "Reason": exit_sig['Reason']
                }
                # Find entry from open_trades list
                for t in open_trades:
                    if t['Symbol'] == exit_sig['Symbol']:
                        trade_record['Entry'] = t['Entry']
                        break
                        
                sheets_db.archive_trade(trade_record)
                sheets_db.delete_trade(exit_sig['Symbol'])
                print("      > Trade Closed & Archived.")
                current_count -= 1 # Free up slot
    
    # 3. CHECK SLOTS & ENTER NEW
    MAX_TRADES = 3
    open_slots = MAX_TRADES - current_count
    
    print(f"2. Slots Logic: {current_count}/{MAX_TRADES} used. {open_slots} free.")
    
    if open_slots > 0:
        print("   > Scanning for Opportunities...")
        results = engine.scan()
        if len(results) > 0:
            # SAVE RESULTS TO DB FOR DASHBOARD
            sheets_db.save_scan_results(results[:20]) # Save Top 20 for speed/relevance
            
            # Filter for TQS >= 8 for Auto-Entry
            # Filter for TQS >= 8 for Auto-Entry
            high_qual = [x for x in results if x['TQS'] >= 8]
            high_qual.sort(key=lambda x: x['TQS'], reverse=True)
            
            # Take top N = open_slots
            picks = high_qual[:open_slots]
            
            for pick in picks:
                # Check if not already in portfolio (Double check)
                is_owned = any(t['Symbol'] == pick['Symbol'] for t in open_trades)
                if not is_owned:
                    print(f"   🚀 AUTO ENTRY: {pick['Symbol']} (TQS {pick['TQS']})")
                    sheets_db.add_trade(
                        pick['Symbol'], 
                        pick['Price'], 
                        1, 
                        pick['Stop'],
                        pick['TQS']
                    )
                    # Log to Daily for record
                    # We can also add a 'TradeLog' entry if we want separate from DailyLog
        else:
            print("   > No scan results found.")
    else:
        print("   > Slots Full. No new entries.")

    print("✅ Bot Cycle Complete.")

if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print(f"Bot Crash: {e}")
