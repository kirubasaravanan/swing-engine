import sheets_db
import pandas as pd

print("--- DEBUG READ START ---")
data, updated, err = sheets_db.fetch_scan_results()

if err:
    print(f"Error: {err}")
else:
    print(f"Updated At: {updated}")
    print(f"Rows Fetched: {len(data)}")
    
    if len(data) > 0:
        row = data[0]
        print(f"Sample Row: {row}")
        print("Types:")
        for k, v in row.items():
            print(f"  {k}: {type(v)} ({v})")
            
print("--- DEBUG READ END ---")
