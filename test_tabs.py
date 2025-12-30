import sheets_db

print("--- TESTING TAB CREATION ---")

# 1. Test LatestScan Creation (by saving mock data)
print("1. Creating 'LatestScan' tab...")
mock_results = [{
    'Symbol': 'TEST_SCAN', 'Price': 100, 'Change': 5.0, 'RSI': 50, 'CHOP': 40,
    'TQS': 10, 'Type': 'TEST', 'Stop': 90, 'Entry': 100, 'Confidence': 'HIGH'
}]
sheets_db.save_scan_results(mock_results)
print("   > LatestScan should be created.")

# 2. Test trades_closed Creation (by archiving mock trade)
print("2. Creating 'trades_closed' tab...")
mock_trade = {
    "Symbol": "TEST_CLOSE", "Entry": 100, "Exit": 110, "PnL": 10.0, 
    "Reason": "TEST", "Date": "2025-01-01"
}
sheets_db.archive_trade(mock_trade)
print("   > trades_closed should be created.")

print("--- DONE ---")
