"""
fix_prevclose2.py — Robust fix using line-by-line search
"""
t = open('app.py', 'r', encoding='utf-8').read()

# Replace kite.ltp with kite.ohlc
if 'kite.ltp(instrument)' in t and 'kite.ohlc' not in t:
    t = t.replace(
        'ltp = kite.ltp(instrument)[instrument]["last_price"]',
        'ohlc_data = kite.ohlc(instrument)[instrument]\n            ltp = ohlc_data["last_price"]\n            prev_cl = ohlc_data["ohlc"]["close"]'
    )
    # Replace the except line to also set prev_cl
    t = t.replace(
        'except: ltp = p["cur_close"]',
        'except:\n            ltp = p["cur_close"]; prev_cl = p["prev_close"]'
    )
    # Replace day_change calc to use prev_cl
    t = t.replace(
        'dc = ((ltp - p["prev_close"]) / p["prev_close"]) * 100 if p["prev_close"] else 0',
        'dc = ((ltp - prev_cl) / prev_cl) * 100 if prev_cl else 0'
    )
    open('app.py', 'w', encoding='utf-8').write(t)
    
    # Verify
    t2 = open('app.py', 'r', encoding='utf-8').read()
    print("  Results:")
    print(f"    kite.ohlc in app.py: {'kite.ohlc' in t2}")
    print(f"    prev_cl in app.py:   {'prev_cl' in t2}")
    print(f"    old kite.ltp gone:   {'kite.ltp(instrument)' not in t2}")
    if 'kite.ohlc' in t2 and 'prev_cl' in t2:
        print("\n  FIXED! kite.ohlc() now provides true previous close.")
    else:
        print("\n  PARTIAL FIX — check app.py manually")
else:
    if 'kite.ohlc' in t:
        print("  Already fixed — kite.ohlc is present")
    else:
        print("  ERROR: kite.ltp not found in expected location")

print("\n  Run: python app.py")
