import sheets_db

print("1. Connecting to DB...")
ws = sheets_db.connect_db()
if ws:
    print("   > Success! Worksheet found.")
else:
    print("   > Failed to connect.")
    exit()

print("2. Adding Test Trade (TEST_SYM)...")
try:
    sheets_db.add_trade("TEST_SYM", 100, 1, 90)
    print("   > Trade Added successfully.")
except Exception as e:
    print(f"   > Write Failed: {e}")

print("3. Fetching Portfolio...")
try:
    pf = sheets_db.fetch_portfolio()
    print(f"   > Active Trades: {len(pf)}")
    print(pf)
except Exception as e:
    print(f"   > Fetch Failed: {e}")
