import time
import market_data
import os
import shutil

# Setup
SYMBOL = "RELIANCE.NS"
CACHE_DIR = "cache"

# Ensure clean start
# if os.path.exists(CACHE_DIR): shutil.rmtree(CACHE_DIR)
# os.makedirs(CACHE_DIR, exist_ok=True)

print(f"🧪 Testing Incremental Fetch for {SYMBOL}...")

# Run 1: Cold (Should Download)
start = time.time()
df1 = market_data.incremental_fetch(SYMBOL, "1d", "3mo")
end = time.time()
t1 = end - start
print(f"Run 1 (Cold): {t1:.4f}s | Rows: {len(df1)}")

# Run 2: Hot (Should Cache Hit)
start = time.time()
df2 = market_data.incremental_fetch(SYMBOL, "1d", "3mo")
end = time.time()
t2 = end - start
print(f"Run 2 (Hot):  {t2:.4f}s | Rows: {len(df2)}")

if t2 < 1.0:
    print("✅ SUCCESS: Cache is working fast (<1s)!")
else:
    print("⚠️ WARNING: Cache might be slow.")
