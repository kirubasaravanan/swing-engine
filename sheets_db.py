import gspread
from oauth2client.service_account import ServiceAccountCredentials
import pandas as pd
import streamlit as st
import datetime
import json
import os

# --- CONFIG ---
SCOPE = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
SHEET_NAME = "Swing_Trades_DB"
CREDENTIALS_FILE = "service_account.json"
DB_FILE = "db.json"

# --- CORE CONNECTION ---
def connect_db():
    """Connects to Google Sheets (Cloud)."""
    creds = None
    if "gcp_service_account" in st.secrets:
            creds_dict = st.secrets["gcp_service_account"]
            creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, SCOPE)
    elif "GCP_SERVICE_ACCOUNT" in os.environ:
            import json as j
            creds_dict = j.loads(os.environ["GCP_SERVICE_ACCOUNT"])
            creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, SCOPE)
    elif os.path.exists(CREDENTIALS_FILE):
            creds = ServiceAccountCredentials.from_json_keyfile_name(CREDENTIALS_FILE, SCOPE)
    else:
            return None # Fail silently, let caller handle
            
    client = gspread.authorize(creds)
    try:
        sheet = client.open(SHEET_NAME)
        # Verify Worksheet Existence
        try: sheet.worksheet("OpenPositions")
        except: pass
        return sheet
    except:
        return None

# --- LOCAL DATABASE LAYER ---
def load_local_db():
    if os.path.exists(DB_FILE):
        try:
            with open(DB_FILE, "r") as f:
                data = json.load(f)
                return data if isinstance(data, dict) else {}
        except: return {}
    return {}

import json
import numpy as np
import pandas as pd

class SafeJSONEncoder(json.JSONEncoder):
    def default(self, obj):
        if isinstance(obj, pd.Series):
            try: return float(obj.iloc[-1]) # Try to get scalar
            except: return str(obj) # Fallback to string repr
        if isinstance(obj, np.integer):
            return int(obj)
        if isinstance(obj, np.floating):
            return float(obj)
        if isinstance(obj, np.ndarray):
            return obj.tolist()
        return super().default(obj)

def save_local_db(data):
    with open(DB_FILE, "w") as f:
        json.dump(data, f, indent=4, cls=SafeJSONEncoder)

# --- SYNC STACK ---
def sync_from_cloud():
    """Downloads ALL data from Cloud -> Local db.json"""
    conn = connect_db()
    if not conn: return False, "Connection Failed"

    try:
        wb = conn
        
        # 1. Portfolio
        try: ws_p = wb.worksheet("OpenPositions")
        except: ws_p = wb.add_worksheet("OpenPositions", 100, 10)
        portfolio = ws_p.get_all_records()
        
        # 2. History
        try: ws_h = wb.worksheet("trades_closed")
        except: ws_h = wb.add_worksheet("trades_closed", 1000, 10)
        history = ws_h.get_all_records()
        
        # 3. Scans
        try: ws_s = wb.worksheet("LatestScan")
        except: ws_s = wb.add_worksheet("LatestScan", 100, 15)
        scans = ws_s.get_all_records()
        
        db = {
            "portfolio": portfolio,
            "history": history,
            "scan_results": scans,
            "last_synced": str(datetime.datetime.now())
        }
        
        # Preserve Watchlist (Local Only for now)
        local_db = load_local_db()
        if "watchlist" in local_db:
            db["watchlist"] = local_db["watchlist"]
        else:
            db["watchlist"] = []

        save_local_db(db)
        return True, "Synced Successfully"
    except Exception as e:
        return False, str(e)

def push_portfolio_to_cloud(portfolio_data):
    """Overwrites OpenPositions in Cloud with Local Data."""
    try:
        wb = connect_db()
        ws = wb.worksheet("OpenPositions")
        ws.clear()
        
        if portfolio_data:
            headers = list(portfolio_data[0].keys())
            ws.append_row(headers)
            rows = [list(x.values()) for x in portfolio_data]
            ws.append_rows(rows)
        return True
    except: return False

# --- READ METHODS (INSTANT) ---

def fetch_portfolio():
    db = load_local_db()
    if db: return db.get("portfolio", [])
    # Fallback to cloud if no local db
    sync_from_cloud()
    return load_local_db().get("portfolio", [])

def fetch_history():
    db = load_local_db()
    if db: return db.get("history", [])
    sync_from_cloud()
    return load_local_db().get("history", [])

def fetch_scan_results():
    db = load_local_db()
    
    # Auto-healing: If no DB, sync first.
    if not db:
        sync_from_cloud()
        db = load_local_db()
        
    if db:
        return db.get("scan_results", []), db.get("last_synced", "Now"), None
    return [], None, "No Data"

# --- WRITE METHODS (SAFE) ---

def add_trade(symbol, entry, qty=1, stop=0, tqs=0):
    # 1. Update Local
    db = load_local_db()
    if not db: sync_from_cloud(); db = load_local_db()
    
    new_row = {
        "Date": datetime.date.today().strftime("%Y-%m-%d"),
        "Symbol": symbol, "Entry": entry, "Qty": qty, "StopLoss": stop,
        "Status": "OPEN", "LTP": entry, "PnL_Pct": 0.0, "ExitPrice": "", "ExitDate": "", "TQS": tqs
    }
    db["portfolio"].append(new_row)
    save_local_db(db)
    
    # 2. Push Cloud (Background Sync)
    push_portfolio_to_cloud(db["portfolio"])
    return True


# --- WATCHLIST METHODS ---
def fetch_watchlist():
    db = load_local_db()
    return db.get("watchlist", [])

def save_watchlist(data):
    db = load_local_db()
    db["watchlist"] = data
    save_local_db(db)

def delete_trade(symbol):
    # 1. Update Local (Precise List Remove)
    db = load_local_db()
    if not db: return
    
    init_len = len(db["portfolio"])
    # Filter out by symbol
    db["portfolio"] = [t for t in db["portfolio"] if t["Symbol"] != symbol]
    
    if len(db["portfolio"]) < init_len:
        save_local_db(db)
        # 2. Push Cloud (Overwrite = No 'wrong row' errors)
        push_portfolio_to_cloud(db["portfolio"])
        print(f"Deleted {symbol} local & cloud.")

def close_trade_db(symbol, exit_price):
    # This was missing in replacement - needed for exit
    db = load_local_db()
    if not db: return False
    
    # Find & Update Local
    found = False
    for t in db["portfolio"]:
        if t['Symbol'] == symbol and t['Status'] == 'OPEN':
             t['Status'] = 'CLOSED'
             t['ExitPrice'] = exit_price
             t['ExitDate'] = datetime.date.today().strftime("%Y-%m-%d")
             found = True
             break
             
    if found:
        # We don't save closed trades in Portfolio list permanently?
        # Actually logic is Archive saves to history. Here we just update?
        # No, usually we delete from portfolio and add to history.
        # But for 'close_trade_db' returning True lets UI handle it.
        # Let's save the logic.
        save_local_db(db)
        return True
    return False

def archive_trade(trade_data):
    # 1. Update Local
    db = load_local_db()
    if not db: sync_from_cloud(); db = load_local_db()
    
    db["history"].append(trade_data)
    save_local_db(db)
    
    # 2. Append to Cloud (Optimized: Just append row)
    try:
        wb = connect_db()
        ws = wb.worksheet("trades_closed")
        row = [
            trade_data.get('Date', ''),
            trade_data.get('Symbol', ''),
            trade_data.get('Entry', 0),
            trade_data.get('Exit', 0),
            trade_data.get('PnL', 0),
            trade_data.get('Reason', 'Manual')
        ]
        ws.append_row(row)
    except: pass

def save_scan_results(results):
    # 1. Local
    db = load_local_db()
    if not db: 
        db = {"portfolio": [], "history": [], "scan_results": []}
    
    db["scan_results"] = results
    db["last_synced"] = str(datetime.datetime.now())
    save_local_db(db)
    
    # 2. Cloud
    try:
        wb = connect_db()
        try: ws = wb.worksheet("LatestScan")
        except: ws = wb.add_worksheet("LatestScan", 100, 15)
        ws.clear()
        
        if results:
            headers = list(results[0].keys())
            ws.append_row(headers)
            rows = [list(r.values()) for r in results]
            ws.append_rows(rows)
    except: pass
    
def test_connection():
    try:
        if connect_db(): return True, "Connected (Cloud + Local Active)"
        return False, "Failed"
    except Exception as e: return False, str(e)
