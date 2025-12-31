import streamlit as st
import pandas as pd
import time
from engine import SwingEngine
import sheets_db

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
@st.cache_resource
def get_engine():
    return SwingEngine()

if 'engine' not in st.session_state:
    st.session_state['engine'] = get_engine()

# --- SIDEBAR ---
with st.sidebar:
    st.header("⚡ Decision Engine")
    
    # Bucket Status
    pf_count = len(st.session_state.get('portfolio', []))
    MAX_SLOTS = 3
    
    # Progress Bar for Bucket
    st.markdown(f"**🪣 Trade Bucket ({pf_count}/{MAX_SLOTS})**")
    st.progress(min(pf_count / MAX_SLOTS, 1.0))
    if pf_count < MAX_SLOTS:
        st.caption(f"🟢 {MAX_SLOTS - pf_count} Slots Available")
    else:
        st.caption("🔴 Bucket Full (Sell to Enter)")
    
    st.write("---")
    
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
        with st.status("🚀 Initializing Scan Sequence...", expanded=True) as status:
            
            st.write("📡 Connecting to Market Data Feed...")
            # Simulate slight delay to show progress (optional, but feels responsive)
            time.sleep(0.5)
            
            st.write("🧠 Decisions Engine: Analyzing Volatility & Trends...")
            
            # Progress Bar
            prog_bar = st.progress(0)
            def update_prog(p):
                prog_bar.progress(p)
                
            results = st.session_state['engine'].scan(progress_callback=update_prog)
            
            st.write(f"🔍 Found {len(results)} potential setups.")
            
            st.write("💾 Saving Intelligence to Cloud Database...")
            sheets_db.save_scan_results(results)
            st.session_state['scan_results'] = results
            
            status.update(label="✅ Scan Complete!", state="complete", expanded=False)
            
        time.sleep(1)
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
    st.subheader("Exit Manager")
    
    with st.expander("> ➕ Add New Position"):
        with st.form("add_pos"):
            c1, c2 = st.columns(2)
            s_sym = c1.text_input("Symbol (e.g. INFY)", "").upper()
            s_entry = c2.number_input("Entry Price", min_value=0.0)
            s_qty = c1.number_input("Qty", min_value=1, value=1)
            s_stop = c2.number_input("Stop Loss", min_value=0.0)
            
            if st.form_submit_button("Add Position"):
                if s_sym and s_entry > 0:
                    tqs = 0 
                    if sheets_db.add_trade(s_sym, s_entry, s_qty, s_stop, tqs):
                        st.success(f"Added {s_sym}")
                        time.sleep(0.5)
                        st.rerun()
                    else:
                        st.error("Failed to add DB")

    # --- UNIFIED PORTFOLIO MANAGER ---
    pos_data = sheets_db.fetch_portfolio()
    
    if pos_data:
        pos_df = pd.DataFrame(pos_data)
        
        # 1. AUTO-ANALYZE & MERGE
        with st.spinner("Analyzing Positions..."):
            try:
                # Run Engine Check
                analysis = st.session_state['engine'].check_exits(pos_df)
                if analysis:
                    an_df = pd.DataFrame(analysis)
                    if 'Symbol' in an_df.columns:
                        an_df = an_df.drop_duplicates(subset=['Symbol'])
                        # Merge actionable data
                        pos_df = pd.merge(pos_df, an_df[['Symbol', 'Action', 'Reason', 'Days', 'Current']], on='Symbol', how='left')
                        
                        # Fill NaNs
                        pos_df['Action'] = pos_df['Action'].fillna('HOLD')
                        pos_df['Reason'] = pos_df['Reason'].fillna('-')
                        pos_df['Days'] = pos_df['Days'].fillna(0).astype(int)
                        # Update LTP
                        pos_df['LTP'] = pos_df['Current'].combine_first(pos_df['LTP'])
            except Exception as e:
                # Non-critical, just show raw DB data
                pass

        # 2. DISPLAY TABLE
        # Columns: Symbol | Entry | LTP | PnL% | Days | Action | Reason
        if 'Action' not in pos_df.columns: pos_df['Action'] = 'HOLD'
        if 'Reason' not in pos_df.columns: pos_df['Reason'] = '-'
        if 'Days' not in pos_df.columns: pos_df['Days'] = 0
        
        # Calculate PnL if missing
        pos_df['LTP'] = pos_df.get('LTP', pos_df['Entry'])
        pos_df['PnL_Pct'] = ((pos_df['LTP'] - pos_df['Entry']) / pos_df['Entry']) * 100
        
        show_cols = ['Symbol', 'Entry', 'LTP', 'PnL_Pct', 'Days', 'Action', 'Reason']
        
        def color_action(val):
            if val == "HOLD": return 'color: #00E676'
            if "EXIT" in val or "BOOK" in val: return 'color: #FF5252; font-weight: bold'
            return ''

        st.dataframe(
            pos_df[show_cols].style.map(color_action, subset=['Action']).format({
                'Entry': '{:.2f}', 'LTP': '{:.2f}', 'PnL_Pct': '{:.2f}%'
            }),
            use_container_width=True,
            height=300
        )
        
        # 3. ACTIONABLE EXITS
        exitable = pos_df[pos_df['Action'] != 'HOLD']
        stock_list = pos_df['Symbol'].unique()
        
        st.markdown("### ⚙️ Actions")
        
        # Auto-Exits
        if not exitable.empty:
            st.markdown("##### ⚠️ Recommended Exits")
            for i, row in exitable.iterrows():
                c1, c2, c3 = st.columns([1, 2, 1])
                with c1: st.write(f"**{row['Symbol']}**")
                with c2: st.write(f"{row['Action']} ({row['Reason']})")
                with c3:
                    if st.button(f"EXECUTE EXIT", key=f"btn_exit_{row['Symbol']}"):
                        if sheets_db.close_trade_db(row['Symbol'], row['LTP']):
                            sheets_db.archive_trade({
                                'Date': row.get('Date', time.strftime("%Y-%m-%d")),
                                'Symbol': row['Symbol'],
                                'Entry': row['Entry'],
                                'Exit': row['LTP'],
                                'PnL': row['PnL_Pct'],
                                'Reason': row['Reason']
                            })
                            sheets_db.delete_trade(row['Symbol'])
                            st.success(f"Exited {row['Symbol']}!")
                            time.sleep(1)
                            st.rerun()

        # Manual Close
        with st.expander("Manual Close / Delete"):
             c1, c2, c3 = st.columns([1, 1, 1])
             with c1:
                 m_sym = st.selectbox("Select Position", stock_list)
             with c2:
                 # Get current LTP
                 curr = pos_df[pos_df['Symbol']==m_sym]['LTP'].iloc[0] if not pos_df.empty else 0
                 m_price = st.number_input("Exit Price", value=float(curr))
             with c3:
                 st.write("")
                 st.write("")
                 if st.button("Close Trade"):
                     entry = pos_df[pos_df['Symbol']==m_sym]['Entry'].iloc[0]
                     pnl = ((m_price - entry)/entry)*100
                     sheets_db.archive_trade({
                        'Date': time.strftime("%Y-%m-%d"),
                        'Symbol': m_sym, 'Entry': entry, 'Exit': m_price,
                        'PnL': pnl, 'Reason': 'Manual'
                     })
                     sheets_db.delete_trade(m_sym)
                     st.success(f"Manually Closed {m_sym}")
                     st.rerun()
                     
    else:
        st.info("Portfolio is empty.")

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
    
    # Filter: Top Picks (Sorted by TQS in Engine)
    top_picks = results[:6]
    
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
        <span style="font-size: 11px; color: #AAAAAA; margin-left: 8px;">1W: <span style="color: #00E676;">{item.get('Weekly %', 0):.1f}%</span></span>
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
        # Ensure Weekly % exists
        if 'Weekly %' not in df_res.columns:
            df_res['Weekly %'] = 0.0
            
        if 'RevTQS' not in df_res.columns:
            df_res['RevTQS'] = 0

        # Reorder
        df_res = df_res[['Symbol', 'Price', 'Change', 'Weekly %', 'TQS', 'RevTQS', 'Confidence', 'Type', 'Entry', 'Stop', 'RSI']]
        
    # Color Helper
    def color_tqs(val):
        if val >= 9: return 'background-color: #00E676; color: black'
        elif val >= 7: return 'background-color: #66BB6A; color: black'
        elif val >= 5: return 'background-color: #FFEA00; color: black'
        else: return 'background-color: #FF5252; color: white'

    # Color TQS in dataframe
    # Color Helper for Weekly %
    def color_weekly(val):
        try:
            v = float(val)
            if v > 10: return 'color: #D50000; font-weight: bold' # Rocket
            if v > 5: return 'color: #00E676; font-weight: bold' # Strong
        except: pass
        return ''

    try:
        st.dataframe(
            df_res.style.map(color_tqs, subset=['TQS'])
                        .map(color_weekly, subset=['Weekly %']),
            use_container_width=True,
            height=500
        )
    except Exception as e:
        st.write(df_res) # Fallback

    except:
        # Fallback for older pandas
        st.dataframe(
            df_res.style.applymap(color_tqs, subset=['TQS']),
            use_container_width=True,
            height=500
        )
