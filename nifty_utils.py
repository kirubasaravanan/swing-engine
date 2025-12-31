import requests
import pandas as pd
import io
import time

# --- FALLBACK LISTS (Expanded to ~150 Stocks for Reliability) ---
FALLBACK_NEXT50 = [
    "ADANIENSOL.NS", "ADANIGREEN.NS", "ADANIPOWER.NS", "ATGL.NS", "AMBUJACEM.NS",
    "ABCAPITAL.NS", "BEL.NS", "BANKBARODA.NS", "BERGEPAINT.NS", "BHARATFORG.NS",
    "BOSCHLTD.NS", "CANBK.NS", "CHOLAFIN.NS", "COLPAL.NS", "DLF.NS",
    "DMART.NS", "GAIL.NS", "GODREJCP.NS", "GODREJPROP.NS", "HAL.NS",
    "HAVELLS.NS", "HDFCAMC.NS", "ICICIGI.NS", "ICICIPRULI.NS", "IOC.NS",
    "IRCTC.NS", "IRFC.NS", "JINDALSTEL.NS", "JIOFIN.NS", "LODHA.NS",
    "MARICO.NS", "MOTHERSON.NS", "MUTHOOTFIN.NS", "NAUKRI.NS", "PIDILITIND.NS",
    "PFC.NS", "PGHH.NS", "PNB.NS", "RECLTD.NS", "SBICARD.NS",
    "SHREECEM.NS", "SIEMENS.NS", "SRF.NS", "TORNTPOWER.NS", "TRENT.NS",
    "TVSMOTOR.NS", "UBL.NS", "UNITEDSPIRITS.NS", "VEDL.NS", "ZOMATO.NS"
]

FALLBACK_MIDCAP = [
    # Finance/Bank
    "PFC.NS", "RECLTD.NS", "YESBANK.NS", "FEDERALBNK.NS", "IDFCFIRSTB.NS", "AUBANK.NS", 
    "BANDHANBNK.NS", "ABCAPITAL.NS", "M&MFIN.NS", "LICHSGFIN.NS", "POONAWALLA.NS",
    "LTFH.NS", "HDFCAMC.NS", "MFSL.NS", "PEL.NS", "MUTHOOTFIN.NS", "CHOLAFIN.NS",
    # Auto/Ind
    "TIINDIA.NS", "BHARATFORG.NS", "ASHOKLEY.NS", "SONACOMS.NS", "APOLLOTYRE.NS",
    "MRF.NS", "BALKRISIND.NS", "ESCORTS.NS", "MOTHERSON.NS", "BOSCHLTD.NS",
    # Tech/Services
    "PERSISTENT.NS", "COFORGE.NS", "KPITTECH.NS", "MPHASIS.NS", "TATAELXSI.NS", 
    "LTTS.NS", "TATACOMM.NS", "PBFINTECH.NS", "NYKAA.NS", "DELHIVERY.NS", "PAYTM.NS",
    "NAUKRI.NS", "ZOMATO.NS",
    # Pharma/Health
    "MAXHEALTH.NS", "LUPIN.NS", "AUROPHARMA.NS", "ALKEM.NS", "FORTIS.NS", 
    "LAURUSLABS.NS", "IPCALAB.NS", "SYNGENE.NS", "GLAND.NS", "BIOCON.NS", 
    "MANKIND.NS", "DRLALPATH.NS", "JSL.NS", "ABBOTINDIA.NS",
    # Power/Infra/Materials
    "ADANIPOWER.NS", "CUMMINSIND.NS", "BHEL.NS", "CGPOWER.NS", "APLAPOLLO.NS", 
    "ASTRAL.NS", "POLYCAB.NS", "JSWENERGY.NS", "NHPC.NS", "TORNTPOWER.NS", 
    "SUZLON.NS", "INDHOTEL.NS", "IRFC.NS", "RVNL.NS", "CONCOR.NS", "GMRINFRA.NS",
    # Realty/Construction
    "MACROTECH.NS", "GODREJPROP.NS", "PRESTIGE.NS", "OBEROIRLTY.NS", "DLF.NS",
    "PHOENIXLTD.NS", "ACC.NS", "DALMIABHARAT.NS", "RAMCOCEM.NS",
    # Oil/Gas/Chem
    "HINDPETRO.NS", "OILINDIA.NS", "PETRONET.NS", "GUJGASLTD.NS", "IGL.NS",
    "ATGL.NS", "DEEPAKNTR.NS", "TATACHEM.NS", "GUJFLUORO.NS", "NAVINFLUOR.NS",
    "SRF.NS", "PIIND.NS", "UPL.NS", "LINDEINDIA.NS", "SOLARINDS.NS"
]

FALLBACK_SMALLCAP = [
    # High Beta / Momentum
    "HINDCOPPER.NS", "JBMA.NS", "COCHINSHIP.NS", "NBCC.NS", "HUDCO.NS", "IRB.NS",
    "NATIONALUM.NS", "NMDC.NS", "SAIL.NS", "HINDZINC.NS", "VEDL.NS",
    # Smallcap Tech/Serv
    "BSOFT.NS", "CYIENT.NS", "INTELLECT.NS", "TANLA.NS", "ROUTE.NS", "ZENSARTECH.NS",
    "CDSL.NS", "BSE.NS", "MCX.NS", "CAMS.NS", "ANGELONE.NS", "IEX.NS",
    # Niche
    "CREDITACC.NS", "GMMPFAUDLR.NS", "EQUITASBNK.NS", "UJJIVANSFB.NS", "RBLBANK.NS",
    "KARURVYSYA.NS", "CUB.NS", "CANFINHOME.NS", "MANAPPURAM.NS",
    # Consumer
    "BLS.NS", "PVRINOX.NS", "DEVYANI.NS", "SAPPHIRE.NS", "WESTLIFE.NS", "VIPIND.NS",
    "CENTURYPLY.NS", "KAJARIACER.NS", "CERA.NS", "BLUESTARCO.NS", "AMBER.NS",
    # Infra/CapGoods
    "KEC.NS", "KALPATPOWR.NS", "TRITURBINE.NS", "ELGIEQUIP.NS", "LAKSHMIMACH.NS",
    "KAJARIACER.NS", "CENTURYPLY.NS", "TEJASNET.NS", "DATA.NS", "SUNDRMFAST.NS",
    "GRSE.NS", "MAZDOCK.NS", "BDL.NS", "ASTRAMICRO.NS", "JWL.NS", "TITAGARH.NS",
    "RKFORGE.NS", "GPIL.NS", "WELCORP.NS", "JINDALSAW.NS", "ABREL.NS", "SWANENERGY.NS"
]

def fetch_nifty_csv(url):
    """
    Fetches unique symbols from NiftyIndices CSV files.
    """
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36",
    }
    try:
        r = requests.get(url, headers=headers, timeout=10)
        if r.status_code == 200:
             df = pd.read_csv(io.StringIO(r.text))
             if 'Symbol' in df.columns:
                 ticks = [t.strip() + ".NS" for t in df['Symbol'].tolist()]
                 return ticks
    except Exception as e:
        print(f"Index Fetch Error: {e}")
        
    return []

def get_midcap100():
    # URL for Nifty Midcap 100
    url = "https://www.niftyindices.com/IndexConstituent/ind_niftymidcap100list.csv"
    syms = fetch_nifty_csv(url)
    if len(syms) < 10:
        print("Using Fallback Midcap List")
        return FALLBACK_MIDCAP
    return syms

def get_smallcap100():
    # URL for Nifty Smallcap 100
    url = "https://www.niftyindices.com/IndexConstituent/ind_niftysmallcap100list.csv"
    syms = fetch_nifty_csv(url)
    if len(syms) < 10:
        print("Using Fallback Smallcap List")
        return FALLBACK_SMALLCAP
    return syms

def get_next50():
    # URL for Nifty Next 50
    url = "https://www.niftyindices.com/IndexConstituent/ind_niftynext50list.csv"
    syms = fetch_nifty_csv(url)
    if len(syms) < 10:
        print("Using Fallback Next 50 List")
        return FALLBACK_NEXT50
    return syms

def get_combined_universe():
    print("Fetching Nifty Next 50, Midcap & Smallcap...")
    next50 = get_next50()
    mid = get_midcap100()
    small = get_smallcap100()
    combined = list(set(next50 + mid + small)) # Remove dupes
    print(f"Total Universe: {len(combined)} stocks")
    return combined
