import gspread
from oauth2client.service_account import ServiceAccountCredentials
import pandas as pd
import streamlit as st
import datetime

# --- CONFIG ---
SCOPE = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
SHEET_NAME = "Swing_Trades_DB"
CREDENTIALS_FILE = "service_account.json"

def connect_db():
    """Connects to Google Sheets and returns the Worksheet object."""
    try:
        creds = ServiceAccountCredentials.from_json_keyfile_name(CREDENTIALS_FILE, SCOPE)
        client = gspread.authorize(creds)
        sheet = client.open(SHEET_NAME)
        # Try to open "OpenPositions" tab, create if missing
        try:
            worksheet = sheet.worksheet("OpenPositions")
            # --- SCHEMA CHECK (Auto-Heal) ---
            # Ensure TQS header exists (Col 11)
            try:
                if worksheet.cell(1, 11).value != "TQS":
                    worksheet.update_cell(1, 11, "TQS")
                    # Also ensure Date header is present
                    if worksheet.cell(1, 1).value != "Date":
                         worksheet.update_cell(1, 1, "Date")
            except:
                # If Col 11 is empty/out of bounds
                worksheet.update_cell(1, 11, "TQS")
                
        except:
            worksheet = sheet.add_worksheet(title="OpenPositions", rows=100, cols=11)
            # Init Headers
            worksheet.append_row(["Date", "Symbol", "Entry", "Qty", "StopLoss", "Status", "LTP", "PnL_Pct", "ExitPrice", "ExitDate", "TQS"])
            
        return worksheet
    except Exception as e:
        print(f"DB Error: {e}")
        return None

def fetch_portfolio():
    """Fetches all OPEN positions."""
    ws = connect_db()
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
    ws_open = connect_db()
    if not ws_open: return []
    
    try:
        wb = ws_open.client.open(SHEET_NAME)
        ws = wb.worksheet("trades_closed")
        data = ws.get_all_records()
        return data
    except:
        return []

def add_trade(symbol, entry, qty=1, stop=0, tqs=0):
    """Adds a new trade."""
    ws = connect_db()
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
    ws = connect_db()
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
    ws = connect_db()
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
    ws = connect_db()
    if not ws: return
    
    try:
        wb = ws.client.open(SHEET_NAME)
        try:
            worksheet = wb.worksheet("LatestScan")
            worksheet.clear()
        except:
            worksheet = wb.add_worksheet(title="LatestScan", rows=100, cols=20)
            
        # Headers
        headers = ["Symbol", "Price", "Change", "RSI", "CHOP", "TQS", "Type", "Stop", "Entry", "Confidence", "Updated"]
        worksheet.append_row(headers)
        
        # Prepare Rows
        import datetime
        timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        
        rows = []
        for r in results:
            rows.append([
                r['Symbol'], r['Price'], r['Change'], r['RSI'], r.get('CHOP', 0), 
                r['TQS'], r['Type'], r['Stop'], r['Entry'], r['Confidence'], timestamp
            ])
            
        worksheet.append_rows(rows)
        print(f"💾 Saved {len(rows)} scan results to DB.")
    except Exception as e:
        print(f"Error saving scan: {e}")

def fetch_scan_results():
    """Reads 'LatestScan'."""
    ws = connect_db()
    if not ws: return [], None
    
    try:
        wb = ws.client.open(SHEET_NAME)
        worksheet = wb.worksheet("LatestScan")
        data = worksheet.get_all_records()
        
        # Get timestamp from first row if exists
        updated_at = "Unknown"
        if data:
            updated_at = data[0].get('Updated', 'Unknown')
            
        return data, updated_at
    except:
        return [], None

def archive_trade(trade_data):
    """Log closed trade to 'trades_closed'"""
    ws_open = connect_db() # Just to get client
    if not ws_open: return False
    
    try:
        wb = ws_open.client.open(SHEET_NAME)
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
