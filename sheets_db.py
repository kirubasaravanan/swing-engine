import gspread
from oauth2client.service_account import ServiceAccountCredentials
import pandas as pd
import streamlit as st
import datetime

import os

# --- CONFIG ---
SCOPE = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
SHEET_NAME = "Swing_Trades_DB"
CREDENTIALS_FILE = "service_account.json"

def test_connection():
    """Returns (Success: bool, Message: str)"""
    try:
        ws = connect_db()
        if not ws:
             return False, "Failed to connect (Check Logs/Secrets)"
        return True, "Connected to Google Sheets ✅"
    except Exception as e:
        return False, str(e)

@st.cache_resource(ttl=600)
def connect_db():
    """Connects to Google Sheets using Streamlit Secrets (Cloud) or Local File."""
    # NO COMPREHENSIVE TRY/EXCEPT HERE
    # Reasons: 
    # 1. cached_resource will cache 'None' if we handle the error and return None.
    # 2. We want it to FAIL so it retries next time or shows the error trace.
    
    creds = None
    # 1. Try Streamlit Secrets (Cloud / Best Practice)
    if "gcp_service_account" in st.secrets:
            creds_dict = st.secrets["gcp_service_account"]
            creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, SCOPE)
    # 2. Try Environment Variable (GitHub Actions / Dotenv)
    elif "GCP_SERVICE_ACCOUNT" in os.environ:
            import json
            creds_dict = json.loads(os.environ["GCP_SERVICE_ACCOUNT"])
            creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, SCOPE)
    elif os.path.exists(CREDENTIALS_FILE):
            # 3. Fallback to Local File
            creds = ServiceAccountCredentials.from_json_keyfile_name(CREDENTIALS_FILE, SCOPE)
    else:
            # Raise exception so it's not cached as None
            available_secrets = list(st.secrets.keys()) if hasattr(st, 'secrets') else "No st.secrets"
            raise ConnectionError(f"No credentials found. Env: {os.environ.keys()}, Secrets: {available_secrets}")
            
    client = gspread.authorize(creds)
    sheet = client.open(SHEET_NAME)
    
    # Try to open "OpenPositions" tab, create if missing
    try:
        worksheet = sheet.worksheet("OpenPositions")
    except gspread.exceptions.WorksheetNotFound:
        worksheet = sheet.add_worksheet(title="OpenPositions", rows=100, cols=11)
        worksheet.append_row(["Date", "Symbol", "Entry", "Qty", "StopLoss", "Status", "LTP", "PnL_Pct", "ExitPrice", "ExitDate", "TQS"])
    
    # --- SCHEMA CHECK (Auto-Heal) ---
    # Ensure TQS header exists (Col 11)
    try:
            if worksheet.cell(1, 11).value != "TQS":
                worksheet.update_cell(1, 11, "TQS")
                if worksheet.cell(1, 1).value != "Date": worksheet.update_cell(1, 1, "Date")
    except Exception as e:
            # This might fail if sheet is empty, safe to ignore or log
            print(f"⚠️ Schema Check Warning: {e}")
        
    return worksheet

def fetch_portfolio():
    """Fetches all OPEN positions."""
    try:
        ws = connect_db()
    except:
        return []
    if not ws: return []
    
    data = ws.get_all_records()
    df = pd.DataFrame(data)
    
    if df.empty: return []
    
    if "Status" in df.columns:
        open_trades = df[df["Status"] == "OPEN"].to_dict('records')
        return open_trades
    return []

def fetch_history():
    """Fetches CLOSED trades."""
    try:
        ws_open = connect_db()
    except:
        return []
    if not ws_open: return []
    
    try:
        wb = ws_open.spreadsheet
        ws = wb.worksheet("trades_closed")
        data = ws.get_all_records()
        return data
    except:
        return []

def add_trade(symbol, entry, qty=1, stop=0, tqs=0):
    """Adds a new trade."""
    try:
        ws = connect_db()
    except:
        return False
    if not ws: return False
    
    date_str = datetime.date.today().strftime("%Y-%m-%d")
    # Date, Symbol, Entry, Qty, StopLoss, Status, LTP, PnL_Pct, ExitPrice, ExitDate, TQS
    row = [date_str, symbol, entry, qty, stop, "OPEN", entry, 0.0, "", "", tqs]
    try:
        ws.append_row(row)
        return True
    except:
        return False

def close_trade_db(symbol, exit_price):
    """Marks a trade as CLOSED."""
    try:
        ws = connect_db()
    except:
        return False
    if not ws: return False
    
    # Find the row
    cell = ws.find(symbol)
    if cell:
        # Update Status (Col 6), ExitPrice (Col 9), ExitDate (Col 10)
        # Note: gspread is 1-indexed
        r = cell.row
        # Check if it's actually OPEN
        status = ws.cell(r, 6).value
        if status == "OPEN":
            ws.update_cell(r, 6, "CLOSED")
            ws.update_cell(r, 9, exit_price)
            ws.update_cell(r, 10, datetime.date.today().strftime("%Y-%m-%d"))
            return True
    return False

def delete_trade(symbol):
    """Deletes a trade from OpenPositions (Recycling slot)."""
    try:
        ws = connect_db()
    except:
        return
    if not ws: return
    
    try:
        cell = ws.find(symbol)
        ws.delete_rows(cell.row)
        print(f"♻️ Recycled Slot: {symbol} removed.")
    except:
        print(f"⚠️ Could not delete {symbol}")

def save_scan_results(results):
    """Overwrites 'LatestScan' with fresh data."""
    if not results: return
    try:
        ws = connect_db()
    except:
        print("Save Error: Connection Failed")
        return
    if not ws: return
    
    try:
        wb = ws.spreadsheet
        try:
            worksheet = wb.worksheet("LatestScan")
            worksheet.clear()
        except:
            worksheet = wb.add_worksheet(title="LatestScan", rows=100, cols=20)
            
        # Headers
        headers = ["Symbol", "Price", "Change", "Weekly %", "RSI", "CHOP", "TQS", "RevTQS", "Type", "Stop", "Entry", "Confidence", "Updated"]
        worksheet.append_row(headers)
        
        # Prepare Rows
        import datetime
        timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        
        rows = []
        for r in results:
            rows.append([
                r['Symbol'], r['Price'], r['Change'], r.get('Weekly %', 0.0), r['RSI'], r.get('CHOP', 0), 
                r['TQS'], r.get('RevTQS', 0), r['Type'], r['Stop'], r['Entry'], r['Confidence'], timestamp
            ])
            
        worksheet.append_rows(rows)
        print(f"Saved {len(rows)} scan results to DB.")
    except Exception as e:
        print(f"Error saving scan: {e}")

def fetch_scan_results():
    """Reads 'LatestScan'. Returns (data, updated_at, error_msg)."""
    try:
        ws = connect_db()
    except Exception as e:
        return [], None, f"DB Connection Failed: {e}"
    if not ws: return [], None, "DB Connection Failed"
    
    try:
        wb = ws.spreadsheet
        worksheet = wb.worksheet("LatestScan")
        data = worksheet.get_all_records()
        
        # Get timestamp from first row if exists
        updated_at = "Unknown"
        if data:
            updated_at = data[0].get('Updated', 'Unknown')
            
        return data, updated_at, None
    except Exception as e:
        return [], None, str(e)

def archive_trade(trade_data):
    """Log closed trade to 'trades_closed'"""
    try:
        ws_open = connect_db() 
    except:
        return False
    if not ws_open: return False
    
    try:
        wb = ws_open.spreadsheet
        try:
            ws_closed = wb.worksheet("trades_closed")
        except:
            ws_closed = wb.add_worksheet("trades_closed", rows=1000, cols=10)
            ws_closed.append_row(["Date", "Symbol", "Entry", "Exit", "PnL", "Reason"])
            
        # Data: [Date, Symbol, Entry, Exit, PnL, Reason]
        ws_closed.append_row([
            trade_data.get('Date', ''),
            trade_data.get('Symbol', ''),
            trade_data.get('Entry', 0),
            trade_data.get('Exit', 0),
            trade_data.get('PnL', 0),
            trade_data.get('Reason', 'AUTO')
        ])
        return True
    except Exception as e:
        print(f"Archive Error: {e}")
        return False
