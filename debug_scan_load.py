import sheets_db
import pandas as pd

print("1. Connecting to DB...")
try:
    data, updated_at = sheets_db.fetch_scan_results()
    print(f"2. Fetch Result: {len(data)} records found.")
    print(f"3. Updated At: {updated_at}")
    
    if data:
        print("4. Sample Data (First Row):")
        print(data[0])
    else:
        print("4. No data found in 'LatestScan' sheet.")

except Exception as e:
    print(f"ERROR: {e}")
