import os
import json
import pandas as pd
import time
import pytz
from datetime import datetime, timedelta
from engine_v2 import SwingEngine
import bulk_deals
import sheets_db
import logging
import socket

# Global Timeout (Prevents indefinite hangs in Cloud)
socket.setdefaulttimeout(15.0)

# --- CONFIG ---
MAX_TRADES = 3
# 09:10 (Pre-Market), 16:30 (Post-Market) added
SCHEDULE_TIMES = ["09:10", "09:30", "11:30", "13:00", "15:10", "16:30"]

# Setup Logging
try:
    import logzero
    from logzero import logger
    log_file = os.path.join(os.getcwd(), 'swing_bot.log')
    logzero.logfile(log_file, maxBytes=1e6, backupCount=3)
except ImportError:
    logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
    logger = logging.getLogger(__name__)

# --- STATE MANAGEMENT ---
STATE_FILE = "bot_state.json"

def load_state():
    if os.path.exists(STATE_FILE):
        try:
            with open(STATE_FILE, 'r') as f: return json.load(f)
        except: pass
    return {"last_run": None, "last_picks": []}

def save_state(state):
    try:
        with open(STATE_FILE, 'w') as f: json.dump(state, f, indent=4)
    except: pass

# --- TIME UTILS ---
IST = pytz.timezone('Asia/Kolkata')

def get_next_schedule_time():
    now = datetime.now(IST)
    candidates = []
    for t_str in SCHEDULE_TIMES:
        h, m = map(int, t_str.split(":"))
        cand = now.replace(hour=h, minute=m, second=0, microsecond=0)
        if cand <= now: cand += timedelta(days=1)
        candidates.append(cand)
    candidates.sort()
    next_run = candidates[0]
    while next_run.weekday() >= 5: next_run += timedelta(days=1)
    delta = (next_run - now).total_seconds()
    return delta, next_run

def get_run_type(run_time):
    t_str = run_time.strftime("%H:%M")
    if t_str == "09:10": return "PRE_MARKET"
    if t_str == "16:30": return "POST_MARKET"
    if t_str == "09:30": return "OPENING"
    return "TRADING"

# --- BOT LOGIC ---

def run_cycle(scheduled_time):
    t_str = scheduled_time.strftime('%H:%M')
    run_type = get_run_type(scheduled_time)
    
    logger.info(f"🤖 RUN: {run_type} ({t_str})")
    
    engine = SwingEngine()
    discord = engine.discord 
    
    if discord: discord.notify_job_status(f"⏰ {run_type} Sequence Started ({t_str})")

    # --- 1. PRE-MARKET (Data Only) ---
    if run_type == "PRE_MARKET":
        logger.info("   > Fetching Pre-Market Data (Gap Analysis)...")
        # In Indian markets, Pre-Open is 9:00-9:08. 9:10 data is usually available.
        try:
            # Updating watchlist here helps capture gap-up candidates early
            engine.update_watchlist()
            if discord: discord.notify_job_status("ℹ️ Pre-Market Watchlist Sync Compete.")
        except Exception as e: logger.error(f"Pre-Market Error: {e}")
        return # EXIT (No Trading)

    # --- 2. OPENING / TRADING (09:30+) ---
    # Update Watchlist at 09:30 too (Official Open reaction)
    if run_type == "OPENING":
        logger.info("   > Opening Bell Watchlist Sync...")
        try: engine.update_watchlist()
        except: pass

    # --- 3. EXITS & ENTRIES (Trading Slots Only) ---
    if run_type in ["OPENING", "TRADING"]:
        # A. EXITS
        # Load Snapshot (Fast Mode)
        data_map = engine.load_snapshot()
        
        # A. EXITS
        logger.info("   > Checking Exits...")
        try:
            trades_df = pd.DataFrame([t for t in sheets_db.fetch_portfolio() if t.get('Status')=='OPEN'])
        except: trades_df = pd.DataFrame()

        if not trades_df.empty:
             trades_df['Entry'] = pd.to_numeric(trades_df['Entry'], errors='coerce')
             # Pass cached data to check_exits
             exits = engine.check_exits(trades_df, data_map=data_map)
             for ex in exits:
                 action = ex.get('Action', 'NONE')
                 if "EXIT" in action or "BOOK" in action:
                     logger.info(f"   🚨 SELL: {ex['Symbol']}")
                     if discord: discord.notify_exit_signal(ex['Symbol'], ex['Reason'], ex['Price'])
                     
                     # 1. ARCHIVE (Save History)
                     try:
                         # Get original trade data
                         row = trades_df[trades_df['Symbol'] == ex['Symbol']].iloc[0]
                         t_data = row.to_dict()
                         
                         # Add Exit Details
                         t_data['Exit'] = ex['Price']
                         t_data['ExitDate'] = datetime.now().strftime("%Y-%m-%d")
                         t_data['Reason'] = ex['Reason']
                         
                         # Calculate Realized PnL
                         entry = float(t_data.get('Entry', 0))
                         qty = float(t_data.get('Qty', 1))
                         exit_p = float(ex['Price'])
                         t_data['PnL'] = (exit_p - entry) * qty
                         
                         sheets_db.archive_trade(t_data)
                         logger.info(f"   📜 Archived {ex['Symbol']} PnL: {t_data['PnL']:.2f}")
                     except Exception as e:
                         logger.error(f"Archive Failed: {e}")

                     # 2. DELETE (Free Slot)
                     sheets_db.delete_trade(ex['Symbol'])
                     
                     # Re-fetch for next step
                     trades_df = trades_df[trades_df['Symbol'] != ex['Symbol']]

        # B. ENTRIES
        current_count = len(trades_df)
        open_slots = MAX_TRADES - current_count
        
        logger.info(f"   > Buckets: {current_count}/{MAX_TRADES}")
        
        if open_slots > 0:
            # Pass cached data to scan
            results = engine.scan(data_map=data_map)
            high_qual = [x for x in results if x['TQS'] >= 8]
            high_qual.sort(key=lambda x: (-x['TQS'], x['Price']))
            
            # Recs Notification
            if high_qual and discord:
                top_msg = ", ".join([f"{x['Symbol']}({x['TQS']})" for x in high_qual[:3]])
                discord.notify_job_status(f"🔎 Top Picks: {top_msg}")

            for pick in high_qual:
                if open_slots <= 0: break
                # Check Local DF
                is_owned = not trades_df.empty and pick['Symbol'] in trades_df['Symbol'].values
                if not is_owned:
                    logger.info(f"   🚀 AUTO BUY: {pick['Symbol']}")
                    sheets_db.add_trade(pick['Symbol'], pick['Price'], 1, pick['Stop'], pick['TQS'])
                    if discord: discord.notify_new_entry(pick['Symbol'], pick['Price'], pick['TQS'])
                    open_slots -= 1
        else:
            logger.info("   > Buckets Full.")

    # --- 4. POST-MARKET (Data Only) ---
    if run_type == "POST_MARKET":
        logger.info("   > Post-Market EOD Sync...")
        try:
            # Run a full scan to cache EOD data effectively
            # And maybe generate a "Closing Report"
            # 1. Gather Monitor List (Watchlist + Portfolio)
            monitor_list = []
            try:
                # Watchlist
                wl = sheets_db.fetch_watchlist()
                monitor_list.extend([w['Symbol'] for w in wl if w.get('status') in ['ACTIVE', 'OPEN_POSITION']])
                # Portfolio (Redundant if status correct, but safe)
                port = sheets_db.fetch_portfolio()
                monitor_list.extend([p['Symbol'] for p in port if p.get('Status') == 'OPEN'])
                monitor_list = list(set(monitor_list)) # Unique
            except: pass
            
            # 2. Filter Top Gainers
            results = engine.scan()
            # Filter results to only monitor list
            my_universe_results = [r for r in results if r['Symbol'] in monitor_list]
            
            # Fallback if specific list empty (show general?) - User requested specific ONLY
            if not my_universe_results: 
                 top_gainers = []
            else:
                 top_gainers = sorted(my_universe_results, key=lambda x: x.get('Weekly %', 0), reverse=True)[:5]
            
            msg = "**🌙 Post-Market Report (My Watchlist)**\n"
            if top_gainers:
                msg += "Top Weekly Gainers:\n"
                for g in top_gainers:
                    msg += f"- {g['Symbol']}: {g['Weekly %']}%\n"
            else:
                msg += "No significant movers in your watchlist today.\n"
            
            # 3. Append Bulk Deals (Filtered)
            try:
                bd_report = bulk_deals.fetch_bulk_deals(filter_symbols=monitor_list)
                msg += "\n" + bd_report
            except: pass
            
            if discord: discord.notify_job_status(msg)
            
        except Exception as e: logger.error(f"Post-Market Error: {e}")

    save_state({"last_run": t_str})
    logger.info("✅ Cycle Complete.")


def main():
    # Check if running in Cloud/CI (GitHub Actions)
    is_ci = os.environ.get('CI') == 'true' or os.environ.get('GITHUB_ACTIONS') == 'true'
    
    if is_ci:
        logger.info("☁️ CLOUD MODE DETECTED (One-Shot Execution)")
        # In Cloud, we rely on CRON.
        # However, GitHub CRON is not second-perfect.
        # We need to decide WHICH slot we are closest to, or if we should just run "Trading Logic".
        # Since CRON triggers at specific times, we assume "Now" is the trigger time.
        
        now = datetime.now(IST)
        # Find closest scheduled slot within last 15 mins?
        # Or just run logic based on current UTC time mapping.
        
        logger.info(f"   Current Time: {now.strftime('%H:%M')}")
        
        # Just run the cycle for "Now"
        # We pass "Now" as the scheduled time
        run_cycle(now)
        
        logger.info("☁️ Cloud Run Complete. Exiting.")
        return

    logger.info(f"🚀 STARTED: Swing Decision Bot")
    logger.info(f"   Slots: {', '.join(SCHEDULE_TIMES)}")
    
    while True:
        try:
            sec, next_time = get_next_schedule_time()
            readable = next_time.strftime('%Y-%m-%d %H:%M:%S')
            
            hrs = int(sec // 3600)
            mins = int((sec % 3600) // 60)
            logger.info(f"💤 Sleeping {hrs}h {mins}m until {readable}...")
            
            time.sleep(sec)
            run_cycle(next_time) 
            time.sleep(60) 
            
        except KeyboardInterrupt: break
        except Exception as e:
            logger.error(f"Error: {e}")
            time.sleep(60)

if __name__ == "__main__":
    main()
