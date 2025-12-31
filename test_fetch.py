from nifty_utils import get_next50, get_midcap100, get_smallcap100

print("Testing Nifty Indices Fetch...")
n50 = get_next50()
print(f"Next 50: {len(n50)}")

mid = get_midcap100()
print(f"Midcap 100: {len(mid)}")

small = get_smallcap100()
print(f"Smallcap 100: {len(small)}")
