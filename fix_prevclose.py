"""
fix_prevclose.py — Fixes the prev_close bug in Pass 2.
Problem: If scan runs before today's candle appears in historical data,
         prev_close becomes day-before-yesterday instead of yesterday.
Fix: Use kite.ohlc() which returns the true previous close directly.
"""

t = open('app.py', 'r', encoding='utf-8').read()

# Replace the LTP fetch block in Pass 2 with ohlc fetch
old_block = """        try:
            ltp = kite.ltp(instrument)[instrument]["last_price"]
        except: ltp = p["cur_close"]

        dc = ((ltp - p["prev_close"]) / p["prev_close"]) * 100 if p["prev_close"] else 0"""

new_block = """        try:
            ohlc_data = kite.ohlc(instrument)[instrument]
            ltp = ohlc_data["last_price"]
            prev_cl = ohlc_data["ohlc"]["close"]
        except:
            ltp = p["cur_close"]
            prev_cl = p["prev_close"]

        dc = ((ltp - prev_cl) / prev_cl) * 100 if prev_cl else 0"""

if old_block in t:
    t = t.replace(old_block, new_block)
    open('app.py', 'w', encoding='utf-8').write(t)
    print("  FIXED: Pass 2 now uses kite.ohlc() for true previous close")
    print("  kite.ohlc() returns yesterday's closing price directly")
    print("  No more off-by-one day errors")
else:
    print("  WARNING: Could not find the exact block to replace")
    print("  Checking if already fixed...")
    if "kite.ohlc" in t:
        print("  Already using kite.ohlc() - no fix needed")
    else:
        print("  ERROR: Manual fix needed")
        print("  The LTP fetch block in Pass 2 doesn't match expected pattern")

print("\n  Run: python app.py")
