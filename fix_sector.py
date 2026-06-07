"""
fix_sector.py — Updates get_sector() regex in app.py
Old: href="/company/compare/..." (broken)
New: icon-industry + <a> tag (working, returns Industry name)
Also clears sector_cache so all sectors re-fetch.
"""
import sqlite3, html as html_mod

# 1. Fix the regex in app.py
t = open('app.py', 'r', encoding='utf-8').read()

old_fn = '''    sector = ""
    try:
        url = f"https://www.screener.in/company/{symbol}/"
        r = http_requests.get(url, headers={"User-Agent": "Mozilla/5.0"}, timeout=8)
        if r.status_code == 200:
            m = re.search(r'href="/company/compare/[^"]*/"[^>]*>([^<]+)</a>', r.text)
            if m:
                sector = m.group(1).strip()
    except: pass'''

new_fn = '''    sector = ""
    try:
        url = f"https://www.screener.in/company/{symbol}/"
        r = http_requests.get(url, headers={"User-Agent": "Mozilla/5.0"}, timeout=8)
        if r.status_code == 200:
            m = re.search(r'icon-industry.*?<a[^>]*>([^<]+)', r.text, re.S)
            if m:
                import html as html_mod
                sector = html_mod.unescape(m.group(1).strip())
    except: pass'''

if old_fn in t:
    t = t.replace(old_fn, new_fn)
    open('app.py', 'w', encoding='utf-8').write(t)
    print("  app.py patched: get_sector() now uses Industry regex")
else:
    print("  WARNING: Could not find old regex pattern in app.py")
    print("  Trying alternate match...")
    # Try matching just the regex line
    old_re = "r'href=\"/company/compare/[^\"]*/"
    if old_re in t:
        t = t.replace(
            '''m = re.search(r'href="/company/compare/[^"]*/"[^>]*>([^<]+)</a>', r.text)
            if m:
                sector = m.group(1).strip()''',
            '''m = re.search(r'icon-industry.*?<a[^>]*>([^<]+)', r.text, re.S)
            if m:
                import html as html_mod
                sector = html_mod.unescape(m.group(1).strip())'''
        )
        open('app.py', 'w', encoding='utf-8').write(t)
        print("  app.py patched (alternate match)")
    else:
        print("  ERROR: Cannot find sector regex in app.py. Manual fix needed.")

# 2. Clear sector cache
try:
    conn = sqlite3.connect('ema9pullback.db')
    conn.execute('DELETE FROM sector_cache')
    conn.commit()
    conn.close()
    print("  sector_cache cleared — will re-fetch all sectors")
except:
    print("  No DB to clear (will create fresh on next scan)")

# 3. Verify
t2 = open('app.py', 'r', encoding='utf-8').read()
print(f"\n  Verification:")
print(f"    icon-industry in app.py: {'icon-industry' in t2}")
print(f"    Old compare regex gone:  {'company/compare' not in t2}")
print(f"\n  Run: python app.py")
