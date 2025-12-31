import json
import os
import datetime
import sheets_db  # Uses existing connection logic

DB_FILE = "db.json"

def sync_down():
    """Pulls ALL data from Google Sheets and saves to db.json"""
    print("[INFO] Connecting to Google Sheets...")
    conn = sheets_db.connect_db()
    if not conn:
        print("[ERROR] Connection Failed.")
        return

    wb = conn
    db = {
        "portfolio": [],
        "history": [],
        "scan_results": [],
        "last_synced": str(datetime.datetime.now())
    }

    # 1. Portfolio
    try:
        print("[INFO] Fetching Portfolio...")
        ws_p = wb.worksheet("OpenPositions")
        db["portfolio"] = ws_p.get_all_records()
    except Exception as e:
        print(f"[WARN] Portfolio Fetch Error: {e} (Assuming Empty)")

    # 2. History
    try:
        print("[INFO] Fetching History...")
        ws_h = wb.worksheet("trades_closed")
        db["history"] = ws_h.get_all_records()
    except:
        print("[INFO] No History found.")

    # 3. Scan Results
    try:
        print("[INFO] Fetching Scan Data...")
        ws_s = wb.worksheet("LatestScan")
        db["scan_results"] = ws_s.get_all_records()
    except:
        print("[INFO] No Scan Results found.")
        
    # Save Localy
    with open(DB_FILE, "w") as f:
        json.dump(db, f, indent=4)
        
    print(f"[SUCCESS] Sync Complete! Data saved to {DB_FILE}")

if __name__ == "__main__":
    sync_down()
