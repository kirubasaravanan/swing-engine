import sheets_db
import gspread

print("--- DEBUG START ---")
try:
    ws = sheets_db.connect_db()
    if ws:
        print(f"Worksheet object: {ws}")
        print(f"Type of ws: {type(ws)}")
        
        # Check spreadsheet
        print(f"ws.spreadsheet: {ws.spreadsheet}")
        
        # Check client
        print(f"ws.client: {ws.client}")
        print(f"Type of ws.client: {type(ws.client)}")
        
        # Check if 'open' exists
        if hasattr(ws.client, 'open'):
            print("✅ ws.client has 'open' method.")
        else:
            print("❌ ws.client MISSING 'open' method.")
            print(f"Dir of ws.client: {dir(ws.client)}")
            
            # Check if it has 'open_by_key' or similar
            
    else:
        print("ws is None (Connection failed elsewhere)")

except Exception as e:
    print(f"CRASH: {e}")
print("--- DEBUG END ---")
