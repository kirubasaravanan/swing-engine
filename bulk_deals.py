import requests
import pandas as pd
import logging
from datetime import datetime

# Configure Logging
logger = logging.getLogger(__name__)

def fetch_bulk_deals(filter_symbols=None):
    """
    Fetches today's Bulk Deals from MoneyControl (NSE).
    Optional: filter_symbols (list of ticker strings like 'RELIANCE', 'TCS')
    Returns a formatted string report.
    """
    url = "https://www.moneycontrol.com/stocks/marketstats/bulk-deals/nse/"
    
    # ... (Headers remain same)
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
    }
    
    try:
        logger.info(f"Fetching Bulk Deals from {url}...")
        response = requests.get(url, headers=headers)
        
        if response.status_code != 200:
            return f"Failed to fetch Bulk Deals (Status: {response.status_code})"
            
        # Parse HTML Tables
        dfs = pd.read_html(response.text)
        
        if not dfs: return "No Deal Data Found."
            
        deal_df = None
        for df in dfs:
            if 'Security Name' in str(df.columns) or 'Company' in str(df.columns):
                deal_df = df
                break
                
        if deal_df is None: return "Could not parse Bulk Deal Table."
            
        deal_df.columns = [str(c) for c in deal_df.columns]
        
        report = "**📢 Bulk Deals Report (NSE)**\n"
        
        count = 0
        accepted_count = 0
        
        # Pre-process filter list (remove .NS, uppercase)
        clean_filter = None
        if filter_symbols:
            clean_filter = [s.replace(".NS","").upper().strip() for s in filter_symbols]
        
        for index, row in deal_df.iterrows():
            if accepted_count >= 10: break # Max 10 relevant deals
            
            try:
                stock = str(row.iloc[0]).strip().upper() # Security Name
                client = row.iloc[1] # Client Name
                algo = str(row.iloc[2]) # Deal Type
                qty = row.iloc[3]
                price = row.iloc[4]
                
                # FILTER LOGIC
                if clean_filter:
                    # Check if stock contains any of our watchlist (fuzzy match or exact?)
                    # Bulk deal names might be full company names (e.g. "Reliance Industries").
                    # Our bucket is "RELIANCE".
                    # Realistically, MoneyControl table usually has Symbol or Name.
                    # If it's Name, we need a map. 
                    # Let's assume for now we might miss some due to Name vs Ticker.
                    # But often they put Ticker in brackets or columns.
                    # Let's try simple inclusion check.
                    
                    found = False
                    for f in clean_filter:
                        # Check exact match or Name containment
                        if f == stock or f in stock or stock in f:
                            found = True
                            break
                    if not found: continue
                
                report += f"- **{stock}**: {algo} {qty} @ {price} ({client})\n"
                accepted_count += 1
                
            except: continue
            
        if accepted_count == 0:
            return "No Bulk Deals found for your Watchlist today."
            
        return report

    except Exception as e:
        logger.error(f"Bulk Deal Fetch Error: {e}")
        return f"Bulk Deal Fetch Error: {e}"

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    print(fetch_bulk_deals())
