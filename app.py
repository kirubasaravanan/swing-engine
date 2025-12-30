import streamlit as st
import pandas as pd
import time
from engine import SwingEngine

# --- PAGE CONFIG ---
st.set_page_config(
    page_title="Swing Decision Engine", 
    page_icon="⚡", 
    layout="wide",
    initial_sidebar_state="expanded"
)

# --- STYLING (Premium Dark/Clean) ---
st.markdown("""
<style>
    .stApp {
        background-color: #0E1117;
        color: #FAFAFA;
    }
    .metric-card {
        background-color: #1E2329;
        padding: 20px;
        border-radius: 10px;
        border: 1px solid #2B313A;
        margin-bottom: 10px;
    }
    .card-title {
        font-size: 1.2em;
        font-weight: bold;
        color: #00A6ED;
    }
    .card-price {
        font-size: 1.5em;
        font-weight: bold;
    }
    .tag-momentum {
        background-color: #26A69A;
        color: white;
        padding: 2px 8px;
        border-radius: 4px;
        font-size: 0.8em;
    }
    .tag-break {
        background-color: #7B1FA2;
        color: white;
        padding: 2px 8px;
        border-radius: 4px;
        font-size: 0.8em;
    <style>
    @import url('https://fonts.googleapis.com/css2?family=Source+Sans+Pro:wght@400;600;700&display=swap');
    
    .block-container { padding-top: 2rem; }
    
    .stButton > button {
        background-color: #262730;
        color: white;
        border: 1px solid #4B4B4B;
        font-family: 'Source Sans Pro', sans-serif;
    }
    .stButton > button:hover {
        background-color: #D50000;
        color: white;
        border-color: #D50000;
    }
    /* Make Metrics Brighter */
    [data-testid="stMetricValue"] {
        color: #FFFFFF !important;
        opacity: 1 !important;
        font-weight: 700 !important;
    }
    [data-testid="stMetricLabel"] {
        color: #AAAAAA !important;
    }
    .tag-rocket {
        background-color: #D50000;
        color: white;
        padding: 2px 8px;
        border-radius: 4px;
        font-size: 0.8em;
        font-weight: bold;
        box-shadow: 0 0 5px #D50000;
        animation: pulse 2s infinite;
    }
    @keyframes pulse {
        0% { opacity: 1; }
        50% { opacity: 0.8; }
        100% { opacity: 1; }
    }
    .tqs-high { color: #00E676; font-weight: bold; }
    .tqs-med { color: #FFEA00; font-weight: bold; }
    .tqs-low { color: #FF5252; font-weight: bold; }
</style>
""", unsafe_allow_html=True)

# --- SESSION STATE ---
if 'engine' not in st.session_state:
    st.session_state['engine'] = SwingEngine()

if 'scan_results' not in st.session_state:
    st.session_state['scan_results'] = []
    # Try Load from DB
    import sheets_db
    cached_res, updated_at, err_msg = sheets_db.fetch_scan_results()
    
    if cached_res:
        st.session_state['scan_results'] = cached_res
        st.session_state['last_update'] = updated_at
    else:
        st.session_state['last_update'] = None
        if err_msg:
             st.session_state['db_error'] = err_msg

# --- SIDEBAR ---
with st.sidebar:
    st.header("⚡ Decision Engine")
    
    # Universe Stats
    u_len = len(st.session_state['engine'].universe)
    st.markdown(f"**⚡ Active Universe**: `{u_len}` Stocks")
    st.caption("Nifty Midcap 100 + Smallcap 100")
    
    with st.expander("Edit / Custom Tickers"):
        ticker_input = st.text_area(
            "Add Custom (Comma Separated)", 
            value=",".join([t.replace(".NS", "") for t in st.session_state['engine'].universe[:10]]),
            height=100
        )
        if st.button("Update List"):
            new_list = [t.strip().upper() for t in ticker_input.split(",") if t.strip()]
            st.session_state['engine'].set_universe(new_list)
            st.rerun()

    st.markdown("---")
    
    # Auto-Update Status
    if st.session_state.get('last_update'):
        st.markdown(f"🟢 **Live Intelligence**")
        st.caption(f"Last Bot Scan: {st.session_state['last_update']}")
    else:
        st.caption("🔴 Bot Data: Waiting for first run...")
        if 'db_error' in st.session_state:
            st.error(f"DB Load Failed: {st.session_state['db_error']}")
        
    with st.expander("🔌 Connection Status"):
        if st.button("Test DB Connection"):
            import sheets_db
            success, msg = sheets_db.test_connection()
            if success:
                st.success(msg)
            else:
                st.error(msg)
                
    if st.button("RUN SCAN 🚀", type="primary"):
        with st.spinner("Crunching Live Data..."):
            results = st.session_state['engine'].scan()
            st.session_state['scan_results'] = results
            st.rerun()


# --- AUTHENTICATION ---
# --- AUTHENTICATION ---
if 'authenticated' not in st.session_state:
    st.session_state['authenticated'] = False

if not st.session_state['authenticated']:
    st.header("🔒 Login")
    pwd = st.text_input("Enter Password", type="password")
    
    if st.button("Login"):
        try:
            correct_pass = st.secrets["passwords"]["admin"]
            if pwd == correct_pass:
                st.session_state['authenticated'] = True
                st.rerun()
            else:
                st.error("Incorrect Password")
        except:
            if pwd == "swing123":
                 st.session_state['authenticated'] = True
                 st.rerun()
            else:
                 st.error("Setup .streamlit/secrets.toml or use default 'swing123'")
    
    st.stop() # CRITICAL: Stop here if not authenticated

# --- MAIN DASHBOARD (Protected) ---
st.title("Swing Decision Radar 📡")

# TABS
# TABS
tab_radar, tab_portfolio, tab_history = st.tabs(["📡 Radar (Entries)", "💼 Portfolio (Exits)", "📜 History (P&L)"])

with tab_history:
    st.header("Trade History (Realized P&L)")
    import sheets_db
    if st.button("Refresh History"):
        st.session_state['history'] = sheets_db.fetch_history()
        
    if 'history' not in st.session_state:
        st.session_state['history'] = sheets_db.fetch_history()
        
    hist = st.session_state['history']
    if hist:
        df_hist = pd.DataFrame(hist)
        # Show Metrics
        if not df_hist.empty:
            total_pnl = df_hist['PnL'].sum() if 'PnL' in df_hist.columns else 0
            win_rate = len(df_hist[df_hist['PnL'] > 0]) / len(df_hist) * 100 if len(df_hist) > 0 else 0
            
            m1, m2 = st.columns(2)
            m1.metric("Total Realized P&L", f"{total_pnl:.2f}%")
            m2.metric("Win Rate", f"{win_rate:.0f}%")
            
            st.dataframe(df_hist, use_container_width=True)
    else:
        st.info("No closed trades yet.")
with tab_portfolio:
    st.header("Exit Manager")
    
    # Initialize Portfolio State from DB (Priority)
    import sheets_db
    
    # Try to load from DB if session is empty or just refreshed
    if 'portfolio' not in st.session_state or not st.session_state['portfolio']:
        db_trades = sheets_db.fetch_portfolio()
        if db_trades:
             # Convert DB format to App format if needed (they are 1:1 here)
             # Map keys if necessary, or just use as is
             st.session_state['portfolio'] = db_trades
    
    if 'portfolio' not in st.session_state:
        st.session_state['portfolio'] = []

    # Input Form (Dropdown + Price)
    # Input Form (Dropdown + Price)
    # Input Form (Dropdown + Price)
    with st.expander("➕ Add New Position", expanded=False):
        c1, c2, c3, c4 = st.columns([1.5, 1, 1, 1])
        uni_options = sorted([t.replace(".NS", "") for t in st.session_state['engine'].universe])
        
        with c1:
            sel_sym = st.selectbox("Select Stock", uni_options)
        with c2:
            sel_price = st.number_input("Entry Price", min_value=0.0, step=0.05)
        with c3:
            # Auto-calc default stop (5%)
            def_stop = sel_price * 0.95 if sel_price > 0 else 0.0
            sel_stop = st.number_input("Stop Loss", value=float(def_stop), step=0.05)
        with c4:
             sel_tqs = st.number_input("TQS Score", min_value=0, max_value=10, value=7)

        if st.button("Add Trade", type="primary", use_container_width=True):
             if sel_price > 0:
                 new_pos = {
                     "Symbol": sel_sym, "Entry": sel_price, 
                     "StopLoss": sel_stop, "TQS": sel_tqs
                 }
                 if not any(p['Symbol'] == sel_sym for p in st.session_state['portfolio']):
                     st.session_state['portfolio'].append(new_pos)
                     try:
                         sheets_db.add_trade(sel_sym, sel_price, 1, sel_stop, sel_tqs)
                         st.success(f"Added {sel_sym}")
                     except Exception as e:
                         st.warning(f"DB Error: {e}")
                     time.sleep(1)
                     st.rerun()

    st.markdown("---")

    # Display & Check Exits
    pf = st.session_state['portfolio']
    
    if pf:
        # 1. LIVE P&L UPDATE & DISPLAY
        # Fetch live prices for all symbols to show Real-Time P&L
        if 'portfolio_data' not in st.session_state or st.button("🔄 Refresh Prices"):
            with st.spinner("Fetching Live Prices..."):
                updated_pf = []
                for p in pf:
                    # Get Live Price
                    try:
                        info = st.session_state['engine'].get_live_price(p['Symbol'] + ".NS")
                        curr_price = info if info else p.get('Current', p['Entry'])
                    except:
                        curr_price = p['Entry']
                    
                    p['Current'] = curr_price
                    p['PnL%'] = ((curr_price - p['Entry']) / p['Entry']) * 100
                    updated_pf.append(p)
                st.session_state['portfolio'] = updated_pf
        
        # Display Table with P&L
        df_pf = pd.DataFrame(st.session_state['portfolio'])
        if not df_pf.empty:
            # Reorder
            # Add Calculated Columns for display if missing
            # Logic: Risk = Entry - Stop
            # Target 1.5R (TQS < 9), Target 2R (TQS >= 9)
            
            # Ensure columns exist (defaults if missing from DB)
            if 'StopLoss' not in df_pf.columns: df_pf['StopLoss'] = df_pf['Entry'] * 0.95
            if 'TQS' not in df_pf.columns: df_pf['TQS'] = 7
            
            # Vectorized Calculation
            df_pf['Risk'] = df_pf['Entry'] - df_pf['StopLoss']
            df_pf['Risk'] = df_pf['Risk'].apply(lambda x: max(x, 0.1)) # Avoid div/0
            
            # Dynamic Target
            def calc_target(row):
                r = row['Risk']
                e = row['Entry']
                tqs = row.get('TQS', 7)
                if tqs >= 9:
                    return e + (2 * r) # 2R
                return e + (1.5 * r) # 1.5R

            df_pf['Target'] = df_pf.apply(calc_target, axis=1)
            df_pf['R:R'] = (df_pf['Target'] - df_pf['Entry']) / df_pf['Risk']
            
            cols_to_show = ['Symbol', 'Entry', 'StopLoss', 'Target', 'Current', 'PnL%', 'R:R']
            df_show = df_pf[cols_to_show].copy()
            
            def color_pnl(val):
                color = '#00E676' if val >= 0 else '#FF5252'
                return f'color: {color}; font-weight: bold'

            st.dataframe(
                df_show.style.applymap(color_pnl, subset=['PnL%']).format({
                    "Entry": "{:.2f}", "Current": "{:.2f}", "PnL%": "{:.2f}%",
                    "StopLoss": "{:.2f}", "Target": "{:.2f}", "R:R": "{:.1f}"
                }),
                use_container_width=True
            )

        # 2. TQS MONITOR (Days + Exit TQS)
        st.markdown("### 🔍 TQS Monitor & Exit Signals")
        if st.button("Analyze Positions (TQS + Days) 🔎", type="primary"):
            pos_df = pd.DataFrame(st.session_state['portfolio'])
            with st.spinner("Calculating Exit TQS & Time Decay..."):
                # Engine now returns ALL rows with status, not just exits
                # Validating engine update...
                # Note: engine.check_exits returns list of dicts.
                monitor_results = st.session_state['engine'].check_exits(pos_df)
                
            if monitor_results:
                df_mon = pd.DataFrame(monitor_results)
                
                # Layout: Symbol | PnL | Days | Exit TQS | Action
                cols = ['Symbol', 'PnL %', 'Days', 'Exit TQS', 'Action']
                # Filter cols if they exist
                cols = [c for c in cols if c in df_mon.columns]
                
                def color_mon(val):
                    if "EXIT" in str(val) or "STOP" in str(val): return 'background-color: #FF5252; color: white'
                    if "HOLD" in str(val): return 'background-color: #00E676; color: black'
                    return ''
                
                st.dataframe(
                    df_mon[cols].style.applymap(color_mon, subset=['Action']),
                    use_container_width=True
                )
            else:
                st.info("No active data to analyze.")

        # 3. MANUAL ACTIONS
        st.markdown("### ⚙️ Position Actions")
        with st.expander("Close or Delete Position", expanded=True):
            c1, c2, c3, c4 = st.columns([1.5, 1, 1, 1])
            active_syms = [p['Symbol'] for p in st.session_state['portfolio']]
            
            with c1:
                close_sym = st.selectbox("Select Position", active_syms)
            with c2:
                # Find current price of selected
                curr_p = next((p['Current'] for p in st.session_state['portfolio'] if p['Symbol'] == close_sym), 0.0)
                exit_price = st.number_input("Exit Price", value=float(curr_p), step=0.05)
            
            with c3:
                st.markdown("<div style='height: 28px'></div>", unsafe_allow_html=True)
                if st.button("🚫 Close (Sell)", type="primary"):
                    entry_p = next((p['Entry'] for p in st.session_state['portfolio'] if p['Symbol'] == close_sym), 0.0)
                    pnl_amt = exit_price - entry_p
                    pnl_pct = (pnl_amt / entry_p) * 100
                    
                    trade_record = {
                        "Symbol": close_sym, "Entry": entry_p, "Exit": exit_price,
                        "PnL": pnl_pct, "Reason": "Manual Close", "Date": time.strftime("%Y-%m-%d")
                    }
                    try:
                        sheets_db.archive_trade(trade_record)
                        sheets_db.delete_trade(close_sym)
                        st.session_state['portfolio'] = [p for p in st.session_state['portfolio'] if p['Symbol'] != close_sym]
                        st.success(f"Closed {close_sym}. PnL: {pnl_pct:.2f}%")
                        time.sleep(1)
                        st.rerun()
                    except Exception as e:
                        st.error(f"Error: {e}")
                        
            with c4:
                st.markdown("<div style='height: 28px'></div>", unsafe_allow_html=True)
                if st.button("🗑️ Delete (Mistake)"):
                    try:
                        sheets_db.delete_trade(close_sym)
                        st.session_state['portfolio'] = [p for p in st.session_state['portfolio'] if p['Symbol'] != close_sym]
                        st.info(f"Deleted {close_sym} without P&L impact.")
                        time.sleep(1)
                        st.rerun()
                    except Exception as e:
                        st.error(f"Error: {e}")

    else:
        st.info("Portfolio empty. Add positions above.")

with tab_radar:
    results = st.session_state['scan_results']

if len(results) == 0:
    st.info("Hit 'RUN SCAN' to fetch live opportunities.")
else:
    # --- METRICS ROW ---
    col1, col2, col3 = st.columns(3)
    c_high = len([r for r in results if r['Confidence'] == 'EXTREME'])
    c_med = len([r for r in results if r['Confidence'] == 'HIGH'])
    
    col1.metric("Opportunities Found", len(results))
    col2.metric("Extreme Confidence (TQS 9-10)", c_high)
    col3.metric("High Confidence (TQS 7-8)", c_med)
    
    st.markdown("---")
    
    # --- CARDS VIEW (Top Picks) ---
    st.subheader("🔥 Top Picks")
    
    # Filter: Prioritize ROCKET LAUNCH
    # We want to force bubble up ROCKET LAUNCH even if TQS is slightly lower (e.g. 8 vs 10)
    # But usually TQS will be high.
    
    # Sort with custom logic: ROCKET first, then Score
    def sort_key(x):
        is_rocket = 100 if "ROCKET" in x['Type'] else 0
        return is_rocket + x['TQS']
        
    sorted_top = sorted(results, key=sort_key, reverse=True)
    top_picks = sorted_top[:6]
    
    cols = st.columns(3)
    for i, item in enumerate(top_picks):
        with cols[i % 3]:
            # Card HTML - Premium Design matching User Request
            
            # Colors
            p_color = "#00F0FF" if "ROCKET" in item['Type'] else "#00E676"
            
            # Format Prices
            price = float(item['Price'])
            chg = float(item['Change'])
            chg_str = f"{chg:+.2f}%"
            chg_color = "#00E676" if chg >= 0 else "#FF5252"
            
            # Target/Stop (Calculated 2R for display)
            risk = max(price - item['Stop'], price*0.01)
            target = price + (2 * risk)
            
            # Font: Source Sans Pro (Injected in CSS)
            
            # Card HTML - No Indentation Issue
            card_html = f"""
<div style="background-color: #161B22; border: 1px solid #30363D; border-radius: 6px; padding: 12px; margin-bottom: 12px; color: #C9D1D9; font-family: 'Source Sans Pro', sans-serif;">
    <div style="display: flex; justify-content: space-between; align-items: start; margin-bottom: 6px;">
        <div style="font-size: 16px; font-weight: 700; color: #FFFFFF; letter-spacing: 0.5px;">{item['Symbol']}</div>
        <div style="font-size: 12px; color: #8B949E; text-align: right;">
            <span style="color: {p_color}; font-weight: 600;">TQS {item['TQS']}</span>
        </div>
    </div>
    <div style="margin-bottom: 6px;">
        <span style="font-size: 20px; font-weight: 600; color: #FFFFFF;">₹{price:.1f}</span>
        <span style="font-size: 13px; color: {chg_color}; font-weight: 600; margin-left: 4px;">({chg_str})</span>
    </div>
    <div style="font-size: 11px; color: #8B949E; margin-bottom: 10px;">
        RSI: <span style="color: #E6EDF3;">{item['RSI']:.1f}</span> <span style="color: #484F58;">|</span> 
        CHOP: <span style="color: #E6EDF3;">{item.get('CHOP', 0):.1f}</span>
    </div>
    <div style="margin-bottom: 10px;">
        <span style="background-color: #1F6FEB20; color: #58A6FF; padding: 2px 6px; border-radius: 4px; font-size: 10px; font-weight: 700; text-transform: uppercase;">
            {item['Type'].replace("🚀", "").strip()}
        </span>
    </div>
    <div style="border-top: 1px solid #21262D; padding-top: 8px; font-size: 10px; color: #8B949E; display: flex; justify-content: space-between;">
        <span>Stop: {item['Stop']:.2f}</span>
        <span>Target: {price + (2 * risk):.1f}</span>
    </div>
</div>
"""
            st.markdown(card_html, unsafe_allow_html=True)

    # --- LIST VIEW ---
    st.markdown("### 📋 Full Scan Results")
    
    df_res = pd.DataFrame(results)
    if not df_res.empty:
        # Reorder
        df_res = df_res[['Symbol', 'Price', 'Change', 'TQS', 'Confidence', 'Type', 'Entry', 'Stop', 'RSI']]
        
    # Color Helper
    def color_tqs(val):
        if val >= 9: return 'background-color: #00E676; color: black'
        elif val >= 7: return 'background-color: #66BB6A; color: black'
        elif val >= 5: return 'background-color: #FFEA00; color: black'
        else: return 'background-color: #FF5252; color: white'

    # Color TQS in dataframe
    try:
        st.dataframe(
            df_res.style.map(color_tqs, subset=['TQS']),
            use_container_width=True,
            height=500
        )
    except:
        # Fallback for older pandas
        st.dataframe(
            df_res.style.applymap(color_tqs, subset=['TQS']),
            use_container_width=True,
            height=500
        )
