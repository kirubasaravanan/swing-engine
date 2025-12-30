import yfinance as yf
import pandas as pd

def debug_yf():
    tickers = ["RELIANCE.NS", "INFY.NS", "TCS.NS"]
    print(f"Fetching: {tickers}")
    
    # 1. Try Batch
    print("\n--- BATCH ATTEMPT ---")
    df = yf.download(tickers, period="5d", interval="1d", group_by='ticker', progress=False)
    print("Empty?", df.empty)
    print("Columns:", df.columns)
    print("Head:\n", df.head())
    
    # 2. Try Single
    print("\n--- SINGLE ATTEMPT ---")
    df_s = yf.download("RELIANCE.NS", period="5d", interval="1d", progress=False)
    print("Empty?", df_s.empty)
    print("Columns:", df_s.columns)
    print("Head:\n", df_s.head())

if __name__ == "__main__":
    debug_yf()
