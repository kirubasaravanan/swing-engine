try:
    import gspread
    import oauth2client
    print("SUCCESS: Modules found.")
except ImportError as e:
    print(f"FAIL: {e}")
