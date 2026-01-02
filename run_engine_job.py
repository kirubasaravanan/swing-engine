import os
import sys
import time
import json
import pandas as pd
import shutil
import argparse
from datetime import datetime
import logging

# Setup Logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler("engine_job.log"),
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger(__name__)

import socket

# Helpers
# Set global timeout for all socket operations (requests, etc)
# This prevents indefinite hangs on GLENMARK.NS or others
socket.setdefaulttimeout(15.0)

# Constants
CACHE_DIR = "cache"
RAW_DIR = os.path.join(CACHE_DIR, "raw")
STATUS_FILE = os.path.join(CACHE_DIR, "engine_status.json")
UI_CACHE_PREFIX = "ui_"
ENGINE_CACHE_PREFIX = "engine_"

# Ensure directories
os.makedirs(CACHE_DIR, exist_ok=True)
os.makedirs(RAW_DIR, exist_ok=True)

def write_status(state, progress, mode="full", error=None):
    """Writes the current engine state to JSON."""
    status = {
        "state": state,
        "last_updated": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "progress": progress,
        "mode": mode,
        "error": str(error) if error else None
    }
    
    # Atomic Write: Write to temp file then rename
    # This prevents app.py from reading an empty/partial file during the write operation
    tmp_file = STATUS_FILE + ".tmp"
    try:
        with open(tmp_file, "w") as f:
            json.dump(status, f)
        os.replace(tmp_file, STATUS_FILE)
    except Exception as e:
        logger.error(f"Failed to write status: {e}")

def get_universe(mode="full"):
    """
    Loads the universe based on mode.
    Mode: 
     - full: All stocks in engine definition.
     - watchlist: Only stocks in watchlist + portfolio.
    """
    try:
        # Import engine lazily to avoid heavy init if not needed
        # We need to access the 'universe' property from engine_v2
        import engine_v2
        eng = engine_v2.SwingEngine()
        
        full_universe = eng.universe
        
        if mode == "full":
            return full_universe
            
        elif mode == "watchlist":
            import sheets_db
            watchlist = sheets_db.fetch_watchlist()
            portfolio = sheets_db.fetch_portfolio()
            
            wl_syms = [x['Symbol'] for x in watchlist if x.get('status') == 'ACTIVE'] if watchlist else []
            pf_syms = [x['Symbol'] for x in portfolio] if portfolio else []
            
            # Combine and clean
            targets = list(set(wl_syms + pf_syms))
            # Ensure they are in the full universe (optional, but good for safety) or just append .NS
            final_list = []
            for t in targets:
                t_clean = t.replace(".NS", "") + ".NS"
                final_list.append(t_clean)
                
            logger.info(f"Watchlist Mode: Found {len(final_list)} targets.")
            return final_list
            
    except Exception as e:
        logger.error(f"Error loading universe: {e}")
        return []
    
    return []

def aggregate_and_swap(tickers, mode):
    """
    Reads raw parquet files for all tickers and combines them into monolithic files.
    Then performs atomic swap to UI files.
    """
    logger.info("Starting Aggregation...")
    
    # We need to aggregate 1d, 1h, 15m
    timeframes = ["1d", "1h", "15m"]
    
    for tf in timeframes:
        combined_data = [] # List of DFs (or dicts?) 
        # Better to store as Dict of DFs in memory then save? 
        # Parquet can save a DataFrame. If we want a K-V store, we might need a specific structure.
        # Approach: We will save a huge DataFrame with a 'Symbol' column, or a MultiIndex.
        # MultiIndex (Symbol, Date) is best for bulk reading.
        
        valid_dfs = []
        
        for ticker in tickers:
            clean_sym = ticker.replace(".NS", "")
            path = os.path.join(RAW_DIR, f"{clean_sym}_{tf}.parquet")
            
            if os.path.exists(path):
                try:
                    df = pd.read_parquet(path)
                    if not df.empty:
                        # Add Symbol column for MultiIndex
                        df['Symbol'] = ticker
                        valid_dfs.append(df)
                except Exception as e:
                    logger.warning(f"Failed to read {path}: {e}")
        
        if not valid_dfs:
            logger.warning(f"No data found for TF {tf}")
            continue
            
        # Concatenate
        try:
            full_df = pd.concat(valid_dfs)
            # Set MultiIndex: Symbol, Date/Index
            # Reset index first to ensure Date is a column if it's currently the index
            if full_df.index.name != 'Symbol': # Assuming Date is index
                 full_df = full_df.reset_index()
            
            # Ensure Date column name is standard (e.g. 'Date' or 'Datetime')
            # yfinance usually gives 'Date' or 'Datetime'
            date_col = 'Date' if 'Date' in full_df.columns else 'Datetime'
            if date_col not in full_df.columns:
                 # Fallback: look for index name
                 date_col = 'index'
            
            # Create standardized Parquet
            # We will use Symbol + Date as composite key if possible, or just partition?
            # For simplicity: Keep flat with Symbol column. User can filter.
            # But converting to MultiIndex (Symbol, Date) is faster for lookup.
            if 'Symbol' in full_df.columns and date_col in full_df.columns:
                full_df.set_index(['Symbol', date_col], inplace=True)
            
            # Write to Engine Staging
            engine_path = os.path.join(CACHE_DIR, f"{ENGINE_CACHE_PREFIX}{tf}.parquet")
            full_df.to_parquet(engine_path)
            
            # Atomic Swap to UI
            ui_path = os.path.join(CACHE_DIR, f"{UI_CACHE_PREFIX}{tf}.parquet")
            # Copy to temp, then move
            tmp_path = ui_path + ".tmp"
            shutil.copy2(engine_path, tmp_path)
            shutil.move(tmp_path, ui_path)
            
            logger.info(f"Swapped {tf} cache with {len(valid_dfs)} symbols.")
            
        except Exception as e:
            logger.error(f"Aggregation Failed for {tf}: {e}")

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--mode", default="full", choices=["full", "watchlist"], help="Scan mode")
    args = parser.parse_args()
    
    mode = args.mode
    logger.info(f"Starting Engine Job. Mode: {mode}")
    
    try:
        # 1. Start
        write_status("RUNNING", "0%", mode)
        
        try:
            from discord_bot import DiscordBot
            DiscordBot().notify_job_status(f"🚀 Background Scan Started (Mode: {mode})")
        except: pass
        
        # 2. Get Universe
        universe = get_universe(mode)
        logging.info(f"Universe Size: {len(universe)}")
        
        if not universe:
            logger.warning("Empty Universe!")
            write_status("COMPLETED", "No Data", mode)
            return

        # 2a. Get VIP Universe (Watchlist + Portfolio) for Deep Data
        vip_universe = set()
        if mode == "full":
            try:
                vip_list = get_universe(mode="watchlist")
                vip_universe = set(vip_list)
                logging.info(f"VIP Universe (Deep Scan): {len(vip_universe)} stocks")
            except: pass

        # 3. Sequential Fetch
        import market_data
        
        # 3. Two-Phase Scan Strategy
        import market_data
        import engine_v2
        
        # Temp engine for Light TSQ check
        temp_eng = engine_v2.SwingEngine()
        
        deep_scan_candidates = set()
        total = len(universe)
        
        # --- PHASE 1: BROAD SCAN (Daily Data Only) ---
        write_status("RUNNING", "Phase 1: Broad Scan (Daily)...", mode)
        
        for i, ticker in enumerate(universe):
            pct = int((i / total) * 50) # First 50% of progress bar
            write_status("RUNNING", f"Daily Scan {i}/{total} ({pct}%)", mode)
            
            try:
                logger.info(f"[{i}/{total}] Fast Fetch {ticker}...")
                
                # Fetch Daily (Incremental) - Stores to Parquet
                df_daily = market_data.incremental_fetch(ticker, "1d", "1y")
                
                # Check for Deep Scan Eligibility
                is_vip = ticker in vip_universe
                is_high_potential = False
                
                if not df_daily.empty and len(df_daily) > 50:
                    # Quick TSQ Check
                    light_tqs = temp_eng.calculate_tqs_daily_only(df_daily)
                    if light_tqs >= 5: # As per user request: TSQ > 5
                        is_high_potential = True
                
                if is_vip or is_high_potential:
                    deep_scan_candidates.add(ticker)
                    
                time.sleep(0.25) # Fast throttle for Daily
                
            except Exception as e:
                logger.error(f"Daily Fetch failed for {ticker}: {e}")

        # --- PHASE 2: DEEP SCAN (Hourly/15m for Candidates) ---
        write_status("RUNNING", "Phase 2: Deep Scan (Intraday)...", mode)
        
        deep_list = list(deep_scan_candidates)
        total_deep = len(deep_list)
        logger.info(f"Deep Scan Candidates: {total_deep} stocks")
        
        for i, ticker in enumerate(deep_list):
            pct = 50 + int((i / total_deep) * 40) # 50% to 90%
            write_status("RUNNING", f"Deep Scan {i}/{total_deep} ({pct}%)", mode)
            
            try:
                logger.info(f"[{i}/{total_deep}] Deep Fetch {ticker}...")
                
                # Fetch Hourly (1 Month) - Optimized Storage
                market_data.incremental_fetch(ticker, "1h", "1mo")
                
                # Fetch 15m (5 Days)
                market_data.incremental_fetch(ticker, "15m", "5d")
                
                time.sleep(1.0) # Slower throttle for heavy data
                
            except Exception as e:
                logger.error(f"Deep Fetch failed for {ticker}: {e}")
                
        # 4. Aggregation & Swap
        write_status("RUNNING", "Aggregating...", mode)
        aggregate_and_swap(universe, mode)
        
        # 5. Analysis (Heavy Lifting)
        write_status("RUNNING", "Analyzing Market...", mode)
        
        try:
            import engine_v2
            import sheets_db # Needed for saving results
            
            # Re-init engine (clean state)
            eng = engine_v2.SwingEngine()
            
            # Load the data we just aggregated (Snapshot)
            data_map = eng.load_snapshot()
            
            if data_map:
                logger.info(f"Loaded Snapshot Data. 1D: {len(data_map.get('1d', []))}")
                
                # A. Run Scan
                logger.info("Running Deep Scan...")
                
                def scan_progress(pct_float):
                    # Map 0.0-1.0 to text progress
                    p_text = f"Analyzing {int(pct_float*100)}%"
                    write_status("RUNNING", p_text, mode)
                    
                scan_results = eng.scan(data_map=data_map, progress_callback=scan_progress)
                
                # Save Scan Results
                sheets_db.save_scan_results(scan_results)
                logger.info(f"Saved {len(scan_results)} scan results.")
                
                # B. Run Portfolio Analysis
                logger.info("Analyzing Portfolio...")
                portfolio = sheets_db.fetch_portfolio()
                
                if portfolio is not None and len(portfolio) > 0:
                    pf_df = pd.DataFrame(portfolio)
                    analysis = eng.check_exits(pf_df, data_map=data_map)
                    
                    # Save Portfolio Analysis to JSON (New File for UI to load instantly)
                    # We can use sheets_db or just a local json
                    pf_analysis_path = os.path.join(CACHE_DIR, "ui_portfolio_analysis.json")
                    with open(pf_analysis_path, "w") as f:
                        # Convert to list of dicts if not already
                        if isinstance(analysis, pd.DataFrame):
                             analysis = analysis.to_dict(orient='records')
                        json.dump(analysis, f)
                    logger.info(f"Saved {len(analysis)} portfolio signals.")
            else:
                logger.warning("Snapshot load failed. Skipping analysis.")

        except Exception as e:
            logger.error(f"Analysis Phase Failed: {e}")
            # Non-fatal? Or fatal? Let's treat as non-fatal for now to allow 'COMPLETED' for data
            pass
        
        # 6. Complete
        write_status("COMPLETED", "100%", mode)
        logger.info("Job Completed Successfully.")
        
        # --- DISCORD ALERTS ---
        try:
            from discord_bot import DiscordBot
            discord = DiscordBot()
            
            # 1. Job Complete
            discord.notify_job_status("✅ Background Scan Completed Successfully.")
            
            # 2. Top Picks (TSQ 9-10)
            if 'scan_results' in locals() and scan_results:
                discord.notify_scan_complete(scan_results)
                
            # 3. Market Snapshot
            if 'portfolio' in locals() and portfolio:
                 pf_count = len(portfolio)
            else: pf_count = 0
            
            # Watchlist count (Estimate from vip_universe or load)
            wl_count = len(vip_universe) if 'vip_universe' in locals() else 0
            
            # High TSQ count
            high_tsq = len([c for c in scan_results if int(c.get('TQS', 0)) >= 9]) if 'scan_results' in locals() else 0
            
            discord.notify_market_update(pf_count, wl_count, high_tsq)
            
        except Exception as e:
            logger.error(f"Discord Notification Failed: {e}")
            
    except Exception as e:
        logger.error(f"Job Critical Error: {e}")
        write_status("FAILED", "Error", mode, str(e))
        
        try:
            from discord_bot import DiscordBot
            DiscordBot().notify_job_status(f"❌ Job Failed: {e}", is_error=True)
        except: pass
        
        sys.exit(1)

if __name__ == "__main__":
    main()
