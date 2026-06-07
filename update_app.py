"""
EMA9 Pullback Scanner — update_app.py
Run: python update_app.py
Then: run_scanner.bat

7 Filters:
  1. EMA9 > EMA21
  2. Gap% 4-10%
  3. EMA9 Slope -1.50 to 20%
  4. EMA21 Slope 2 to 15%
  5. LOW within +/-2% of EMA9 + green candle (last 5 days)
  6. LTP vs Prev Close +0.5% to +4%
  7. LTP < EMA9 * 1.06
"""
import os, re

FOLDER = os.path.dirname(os.path.abspath(__file__))

# ── UPDATE CONFIG ──
config_path = os.path.join(FOLDER, "config.py")
cfg = open(config_path, "r", encoding="utf-8").read()

def set_param(text, name, value):
    pat = re.compile(rf"^{name}\s*=\s*[^\n]+", re.MULTILINE)
    if pat.search(text):
        return pat.sub(f"{name} = {value}", text)
    return text + f"\n{name} = {value}\n"

cfg = set_param(cfg, "GAP_PCT_MIN", "4.00")
cfg = set_param(cfg, "GAP_PCT_MAX", "10.00")
cfg = set_param(cfg, "EMA9_SLOPE5_MIN", "-1.50")
cfg = set_param(cfg, "EMA9_SLOPE5_MAX", "20.00")
cfg = set_param(cfg, "EMA21_SLOPE5_MIN", "2.00")
cfg = set_param(cfg, "EMA21_SLOPE5_MAX", "15.00")
cfg = set_param(cfg, "TOUCH_BELOW", "0.02")
cfg = set_param(cfg, "TOUCH_ABOVE", "0.02")
cfg = set_param(cfg, "TOUCH_LOOKBACK", "5")
cfg = set_param(cfg, "INTRADAY_GAIN_MIN", "0.50")
cfg = set_param(cfg, "INTRADAY_GAIN_MAX", "4.00")
cfg = set_param(cfg, "LTP_EMA9_MAX", "6.00")

open(config_path, "w", encoding="utf-8").write(cfg)
print("  config.py updated (including LTP_EMA9_MAX = 6.00)")

# ── VERIFY ──
verify = open(config_path, "r", encoding="utf-8").read()
for p in ["LTP_EMA9_MAX", "INTRADAY_GAIN_MIN", "INTRADAY_GAIN_MAX", "TOUCH_BELOW", "TOUCH_ABOVE"]:
    if p not in verify:
        print(f"  WARNING: {p} missing from config.py!")
    else:
        print(f"  OK: {p} found")

# ── WRITE APP.PY ──
APP = r'''import os, sys, json, time, threading, sqlite3, smtplib, io, re
from datetime import datetime, timedelta, date
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

import pandas as pd
import requests as http_requests
from flask import Flask, render_template_string, jsonify, Response, send_file

from config import *
from auth import get_kite

app = Flask(__name__)
scan_progress = {"running": False, "current": 0, "total": 0, "symbol": "", "phase": ""}
scan_results_cache = []
last_scan_time = ""

def init_db():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("""CREATE TABLE IF NOT EXISTS scan_results (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        scan_date TEXT, symbol TEXT, ltp REAL, ema9 REAL, ema21 REAL,
        gap_pct REAL, ema9_slope REAL, ema21_slope REAL,
        proximity_pct REAL, day_change_pct REAL, sector TEXT DEFAULT '',
        touch_day TEXT DEFAULT '',
        created_at TEXT DEFAULT (datetime('now','localtime'))
    )""")
    c.execute("""CREATE TABLE IF NOT EXISTS scan_log (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        scan_date TEXT, total_stocks INTEGER, passed INTEGER, duration_sec REAL,
        created_at TEXT DEFAULT (datetime('now','localtime'))
    )""")
    c.execute("""CREATE TABLE IF NOT EXISTS sector_cache (
        symbol TEXT PRIMARY KEY, sector TEXT, updated_at TEXT
    )""")
    for col in ["sector TEXT DEFAULT ''", "touch_day TEXT DEFAULT ''"]:
        try: c.execute(f"ALTER TABLE scan_results ADD COLUMN {col}")
        except: pass
    conn.commit(); conn.close()

init_db()

def get_sector(symbol):
    conn = sqlite3.connect(DB_PATH); c = conn.cursor()
    c.execute("SELECT sector FROM sector_cache WHERE symbol = ?", (symbol,))
    row = c.fetchone()
    if row and row[0]: conn.close(); return row[0]
    conn.close()
    sector = ""
    try:
        url = f"https://www.screener.in/company/{symbol}/"
        r = http_requests.get(url, headers={"User-Agent": "Mozilla/5.0"}, timeout=8)
        if r.status_code == 200:
            m = re.search(r'href="/company/compare/[^"]*/"[^>]*>([^<]+)</a>', r.text)
            if m: sector = m.group(1).strip()
    except: pass
    if sector:
        conn = sqlite3.connect(DB_PATH); c = conn.cursor()
        c.execute("INSERT OR REPLACE INTO sector_cache (symbol, sector, updated_at) VALUES (?,?,?)",
                  (symbol, sector, datetime.now().strftime("%Y-%m-%d")))
        conn.commit(); conn.close()
    return sector

def load_symbols():
    if not os.path.exists(NSE_STOCKS_FILE): return []
    try:
        if NSE_STOCKS_FILE.endswith(".csv"):
            df = pd.read_csv(NSE_STOCKS_FILE)
            col = "SYMBOL" if "SYMBOL" in df.columns else df.columns[0]
        else:
            df = pd.read_excel(NSE_STOCKS_FILE); col = df.columns[0]
        syms = df[col].dropna().astype(str).str.strip().tolist()
        return [s for s in syms if s and s != "nan"]
    except: return []

def calc_ema(prices, period):
    if len(prices) < period: return []
    k = 2 / (period + 1)
    ema = [sum(prices[:period]) / period]
    for p in prices[period:]: ema.append(p * k + ema[-1] * (1 - k))
    return ema

def run_scan(console=False):
    global scan_progress, scan_results_cache, last_scan_time
    if scan_progress["running"]: return
    scan_progress = {"running": True, "current": 0, "total": 0, "symbol": "", "phase": "Authenticating..."}

    if console:
        print("\n" + "="*70)
        print("  EMA9 PULLBACK SCANNER")
        print("="*70)
        print("  Authenticating with Zerodha...")

    kite = get_kite()
    if not kite:
        scan_progress = {"running": False, "current": 0, "total": 0, "symbol": "", "phase": "Auth failed"}
        if console: print("  X Auth failed!")
        return
    if console: print("  OK Authenticated\n")

    symbols = load_symbols()
    if not symbols:
        scan_progress = {"running": False, "current": 0, "total": 0, "symbol": "", "phase": "No symbols"}
        return

    total = len(symbols)
    scan_progress["total"] = total
    today = date.today()
    from_date = today - timedelta(days=CANDLE_DAYS)
    start_time = time.time()

    # ── PASS 1 ──
    scan_progress["phase"] = "Pass 1: EMA Gate + Touch"
    if console:
        print("-"*70)
        print(f"  PASS 1: EMA Gate + LOW Touch + Green Candle ({total} stocks)")
        print(f"  Gap: {GAP_PCT_MIN}%-{GAP_PCT_MAX}% | EMA9 Slope: {EMA9_SLOPE5_MIN}%-{EMA9_SLOPE5_MAX}%")
        print(f"  EMA21 Slope: {EMA21_SLOPE5_MIN}%-{EMA21_SLOPE5_MAX}%")
        print(f"  EMA9 Touch: LOW within -{TOUCH_BELOW*100}% to +{TOUCH_ABOVE*100}% (last {TOUCH_LOOKBACK} days)")
        print(f"  Green candle on touch day")
        print(f"  LTP vs Prev Close: +{INTRADAY_GAIN_MIN}% to +{INTRADAY_GAIN_MAX}%")
        print(f"  LTP < EMA9 + {LTP_EMA9_MAX}%")
        print("-"*70)

    pass1 = []
    for idx, sym in enumerate(symbols):
        scan_progress["current"] = idx + 1
        scan_progress["symbol"] = sym
        if console and (idx + 1) % 50 == 0:
            print(f"  [{idx+1}/{total}] Scanning {sym}... (hits: {len(pass1)})")
        try:
            token = _get_instrument_token(kite, sym)
            if not token: continue
            candles = kite.historical_data(instrument_token=token, from_date=from_date, to_date=today, interval="day")
            if not candles or len(candles) < 30: continue

            closes = [c["close"] for c in candles]
            opens  = [c["open"]  for c in candles]
            lows   = [c["low"]   for c in candles]

            ema9_all  = calc_ema(closes, 9)
            ema21_all = calc_ema(closes, 21)
            if not ema9_all or not ema21_all: continue

            offset = 21 - 9
            ema9 = ema9_all[offset:]; ema21 = ema21_all[:]
            ml = min(len(ema9), len(ema21))
            ema9 = ema9[-ml:]; ema21 = ema21[-ml:]
            ac = closes[-ml:]; ao = opens[-ml:]; al = lows[-ml:]
            if len(ema9) < 6 or len(ema21) < 6: continue

            e9 = ema9[-1]; e21 = ema21[-1]
            cur_close = ac[-1]; prev_close = ac[-2] if len(ac) > 1 else cur_close

            if e9 <= e21: continue
            gap = ((e9 - e21) / e21) * 100
            if gap < GAP_PCT_MIN or gap > GAP_PCT_MAX: continue
            s9 = ((ema9[-1] - ema9[-6]) / ema9[-6]) * 100
            if s9 < EMA9_SLOPE5_MIN or s9 > EMA9_SLOPE5_MAX: continue
            s21 = ((ema21[-1] - ema21[-6]) / ema21[-6]) * 100
            if s21 < EMA21_SLOPE5_MIN or s21 > EMA21_SLOPE5_MAX: continue

            td = ""
            lb = min(TOUCH_LOOKBACK, len(ac), len(ema9))
            for d in range(lb):
                dc = ac[-(d+1)]; do = ao[-(d+1)]; dl = al[-(d+1)]; de = ema9[-(d+1)]
                lo = de * (1 - TOUCH_BELOW); hi = de * (1 + TOUCH_ABOVE)
                if lo <= dl <= hi and dc > do:
                    td = f"T-{d}" if d > 0 else "T-0"; break
            if not td: continue

            pass1.append({"symbol": sym, "ema9": e9, "ema21": e21, "gap_pct": gap,
                          "ema9_slope": s9, "ema21_slope": s21, "cur_close": cur_close,
                          "prev_close": prev_close, "touch_day": td})
        except: pass
        if (idx + 1) % 3 == 0: time.sleep(0.35)

    if console:
        print(f"\n  PASS 1 COMPLETE: {len(pass1)}/{total} passed ({round(time.time()-start_time,1)}s)")
        if pass1:
            print(f"  Passed: {', '.join(r['symbol'] for r in pass1[:20])}")
            if len(pass1) > 20: print(f"          ...and {len(pass1)-20} more")
        print()

    # ── PASS 2: LTP checks ──
    scan_progress["phase"] = "Pass 2: LTP checks"
    if console:
        print("-"*70)
        print(f"  PASS 2: LTP vs Prev Close +{INTRADAY_GAIN_MIN}% to +{INTRADAY_GAIN_MAX}%")
        print(f"          LTP < EMA9 + {LTP_EMA9_MAX}% ({len(pass1)} stocks)")
        print("-"*70)

    results = []
    for idx, p in enumerate(pass1):
        sym = p["symbol"]; instrument = f"NSE:{sym}"
        scan_progress["current"] = idx + 1
        scan_progress["total"] = len(pass1)
        scan_progress["symbol"] = sym
        try:
            ltp = kite.ltp(instrument)[instrument]["last_price"]
        except: ltp = p["cur_close"]

        dc = ((ltp - p["prev_close"]) / p["prev_close"]) * 100 if p["prev_close"] else 0
        prox = ((ltp - p["ema9"]) / p["ema9"]) * 100
        cap = p["ema9"] * (1 + LTP_EMA9_MAX / 100)

        f6 = INTRADAY_GAIN_MIN <= dc <= INTRADAY_GAIN_MAX
        f7 = ltp < cap

        if f6 and f7:
            results.append({"symbol": sym, "ltp": round(ltp, 2), "ema9": round(p["ema9"], 2),
                            "ema21": round(p["ema21"], 2), "gap_pct": round(p["gap_pct"], 2),
                            "ema9_slope": round(p["ema9_slope"], 2), "ema21_slope": round(p["ema21_slope"], 2),
                            "proximity_pct": round(prox, 2), "day_change_pct": round(dc, 2),
                            "sector": "", "touch_day": p["touch_day"]})
            status = ">> HIT"
        else:
            reasons = []
            if not f6: reasons.append(f"chg {dc:+.2f}%")
            if not f7: reasons.append(f"LTP {ltp:.0f} > cap {cap:.0f}")
            status = f"X ({', '.join(reasons)})"

        if console:
            print(f"  [{idx+1}/{len(pass1)}] {sym:20s} LTP={ltp:>10.2f}  Chg={dc:>+6.2f}%  Prox={prox:>+6.2f}%  {status}")
        if (idx + 1) % 5 == 0: time.sleep(0.2)

    # ── PASS 3: Sector ──
    if results:
        scan_progress["phase"] = "Pass 3: Sector lookup"
        if console: print(f"\n  PASS 3: Sector lookup for {len(results)} stocks...")
        for idx, r in enumerate(results):
            scan_progress["symbol"] = r["symbol"]; scan_progress["current"] = idx + 1; scan_progress["total"] = len(results)
            sector = get_sector(r["symbol"]); r["sector"] = sector
            if console: print(f"  [{idx+1}/{len(results)}] {r['symbol']:20s} -> {sector or '(unknown)'}")
            time.sleep(0.3)

    elapsed = round(time.time() - start_time, 1)
    scan_date = today.strftime("%Y-%m-%d")

    if console:
        print(f"\n" + "="*70)
        print(f"  FINAL: {len(results)} stocks | Total time: {elapsed}s")
        if results:
            print(f"\n  {'Symbol':<16} {'LTP':>10} {'EMA9':>10} {'Gap%':>8} {'Chg%':>8} {'Prox%':>8} {'Touch':<6} {'Sector'}")
            print(f"  {'-'*90}")
            for r in results:
                print(f"  {r['symbol']:<16} {r['ltp']:>10.2f} {r['ema9']:>10.2f} {r['gap_pct']:>7.2f}% {r['day_change_pct']:>+7.2f}% {r['proximity_pct']:>+7.2f}% {r['touch_day']:<6} {r['sector']}")
        print("="*70 + "\n")

    conn = sqlite3.connect(DB_PATH); c = conn.cursor()
    c.execute("DELETE FROM scan_results WHERE scan_date = ?", (scan_date,))
    for r in results:
        c.execute("""INSERT INTO scan_results (scan_date,symbol,ltp,ema9,ema21,gap_pct,ema9_slope,ema21_slope,proximity_pct,day_change_pct,sector,touch_day)
            VALUES (?,?,?,?,?,?,?,?,?,?,?,?)""",
            (scan_date,r["symbol"],r["ltp"],r["ema9"],r["ema21"],r["gap_pct"],r["ema9_slope"],r["ema21_slope"],r["proximity_pct"],r["day_change_pct"],r["sector"],r["touch_day"]))
    c.execute("INSERT INTO scan_log (scan_date,total_stocks,passed,duration_sec) VALUES (?,?,?,?)",
              (scan_date, len(symbols), len(results), elapsed))
    conn.commit(); conn.close()

    scan_results_cache = results
    last_scan_time = datetime.now().strftime("%d-%b-%Y %I:%M %p")
    if results and GMAIL_SENDER and GMAIL_APP_PASSWORD: send_gmail(results, scan_date)
    scan_progress = {"running": False, "current": len(pass1), "total": len(pass1),
                     "symbol": "Done", "phase": f"Complete: {len(results)} stocks found in {elapsed}s"}

_instrument_cache = {}
def _get_instrument_token(kite, symbol):
    global _instrument_cache
    if not _instrument_cache:
        for inst in kite.instruments("NSE"): _instrument_cache[inst["tradingsymbol"]] = inst["instrument_token"]
    return _instrument_cache.get(symbol)

def send_gmail(results, scan_date):
    try:
        msg = MIMEMultipart("alternative")
        msg["Subject"] = f"EMA9 Pullback: {len(results)} stocks - {scan_date}"
        msg["From"] = GMAIL_SENDER; msg["To"] = GMAIL_RECIPIENT
        rows = ""
        for r in results:
            c = "#4ade80" if r["day_change_pct"] >= 0 else "#f87171"
            rows += f'<tr><td style="padding:6px 10px;border-bottom:1px solid #333"><a href="https://www.tradingview.com/chart/?symbol=NSE%3A{r["symbol"]}" style="color:#22d3ee">{r["symbol"]}</a></td>'
            rows += f'<td style="padding:6px 10px;border-bottom:1px solid #333">{r.get("sector","")}</td>'
            rows += f'<td style="padding:6px 10px;border-bottom:1px solid #333;text-align:right">{r["ltp"]:,.2f}</td>'
            rows += f'<td style="padding:6px 10px;border-bottom:1px solid #333;text-align:right">{r["gap_pct"]:.2f}%</td>'
            rows += f'<td style="padding:6px 10px;border-bottom:1px solid #333;text-align:right;color:{c}">{r["day_change_pct"]:+.2f}%</td>'
            rows += f'<td style="padding:6px 10px;border-bottom:1px solid #333;text-align:right">{r["proximity_pct"]:+.2f}%</td>'
            rows += f'<td style="padding:6px 10px;border-bottom:1px solid #333">{r.get("touch_day","")}</td></tr>'
        html = f'''<html><body style="background:#111;color:#e5e5e5;font-family:monospace;padding:20px">
        <h2 style="color:#22d3ee">EMA9 Pullback: {scan_date}</h2>
        <p>{len(results)} stocks | LTP +{INTRADAY_GAIN_MIN}% to +{INTRADAY_GAIN_MAX}% | LTP &lt; EMA9+{LTP_EMA9_MAX}%</p>
        <table style="border-collapse:collapse;width:100%">
        <tr style="color:#a3a3a3"><th style="padding:8px 10px;text-align:left">Symbol</th>
        <th style="text-align:left;padding:8px">Sector</th><th style="text-align:right;padding:8px">LTP</th>
        <th style="text-align:right;padding:8px">Gap%</th><th style="text-align:right;padding:8px">Chg%</th>
        <th style="text-align:right;padding:8px">Prox%</th><th style="text-align:left;padding:8px">Touch</th></tr>
        {rows}</table></body></html>'''
        msg.attach(MIMEText(html, "html"))
        with smtplib.SMTP_SSL("smtp.gmail.com", 465) as s:
            s.login(GMAIL_SENDER, GMAIL_APP_PASSWORD); s.sendmail(GMAIL_SENDER, GMAIL_RECIPIENT, msg.as_string())
        print(f"  Gmail sent: {len(results)} stocks")
    except Exception as e: print(f"  Gmail error: {e}")

@app.route("/progress")
def progress():
    def stream():
        while True:
            yield f"data: {json.dumps(scan_progress)}\n\n"
            if not scan_progress["running"] and scan_progress["phase"].startswith("Complete"):
                yield f"data: {json.dumps({'done': True})}\n\n"; break
            time.sleep(0.5)
    return Response(stream(), mimetype="text/event-stream")

@app.route("/scan", methods=["POST"])
def trigger_scan():
    if scan_progress["running"]: return jsonify({"status": "already_running"})
    t = threading.Thread(target=run_scan, args=(False,), daemon=True); t.start()
    return jsonify({"status": "started"})

@app.route("/results")
def get_results():
    conn = sqlite3.connect(DB_PATH); c = conn.cursor()
    c.execute("""SELECT symbol,ltp,ema9,ema21,gap_pct,ema9_slope,ema21_slope,proximity_pct,day_change_pct,scan_date,COALESCE(sector,''),COALESCE(touch_day,'')
                 FROM scan_results ORDER BY scan_date DESC, gap_pct ASC LIMIT 500""")
    rows = c.fetchall(); conn.close()
    return jsonify([{"symbol":r[0],"ltp":r[1],"ema9":r[2],"ema21":r[3],"gap_pct":r[4],"ema9_slope":r[5],"ema21_slope":r[6],"proximity_pct":r[7],"day_change_pct":r[8],"scan_date":r[9],"sector":r[10],"touch_day":r[11]} for r in rows])

@app.route("/export")
def export_excel():
    conn = sqlite3.connect(DB_PATH); c = conn.cursor()
    c.execute("""SELECT symbol,ltp,ema9,ema21,gap_pct,ema9_slope,ema21_slope,proximity_pct,day_change_pct,scan_date,COALESCE(sector,''),COALESCE(touch_day,'')
                 FROM scan_results WHERE scan_date=(SELECT MAX(scan_date) FROM scan_results) ORDER BY sector ASC, gap_pct ASC""")
    rows = c.fetchall(); conn.close()
    df = pd.DataFrame(rows, columns=["Symbol","LTP","EMA9","EMA21","Gap%","EMA9 Slope%","EMA21 Slope%","Proximity%","Day Chg%","Date","Sector","Touch Day"])
    buf = io.BytesIO(); df.to_excel(buf, index=False, engine="openpyxl"); buf.seek(0)
    return send_file(buf, download_name=f"EMA9_Pullback_{date.today().strftime('%Y%m%d')}.xlsx", as_attachment=True,
                     mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")

@app.route("/")
def dashboard(): return render_template_string(HTML_TEMPLATE)

HTML_TEMPLATE = r"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>EMA9 Pullback Scanner</title>
<style>
@import url('https://fonts.googleapis.com/css2?family=JetBrains+Mono:wght@300;400;500;600;700&display=swap');
*{margin:0;padding:0;box-sizing:border-box}
body{background:#0a0a0a;color:#e5e5e5;font-family:'JetBrains Mono',monospace;font-size:13px}
.header{background:linear-gradient(135deg,#0f172a,#1e1b4b);padding:20px 28px;border-bottom:1px solid #1e293b}
.header h1{font-size:20px;font-weight:700;color:#22d3ee;letter-spacing:1px}
.header .sub{color:#64748b;font-size:11px;margin-top:4px}
.toolbar{display:flex;gap:12px;align-items:center;padding:14px 28px;background:#111;border-bottom:1px solid #1e293b;flex-wrap:wrap}
.btn{padding:8px 18px;border:none;border-radius:4px;font-family:inherit;font-size:12px;font-weight:600;cursor:pointer;transition:.15s}
.btn-scan{background:#22d3ee;color:#0a0a0a}.btn-scan:hover{background:#06b6d4}
.btn-scan:disabled{background:#334155;color:#64748b;cursor:not-allowed}
.btn-export{background:#1e293b;color:#94a3b8}.btn-export:hover{background:#334155;color:#e2e8f0}
.progress-bar{flex:1;min-width:200px}
.progress-outer{background:#1e293b;border-radius:3px;height:20px;overflow:hidden;position:relative}
.progress-inner{background:linear-gradient(90deg,#0891b2,#22d3ee);height:100%;transition:width .3s;border-radius:3px}
.progress-text{position:absolute;top:0;left:0;right:0;height:100%;display:flex;align-items:center;justify-content:center;font-size:10px;color:#e2e8f0;font-weight:500;text-shadow:0 1px 2px rgba(0,0,0,.5)}
.filter-info{padding:8px 28px;background:#0d1117;border-bottom:1px solid #1a1a1a;font-size:10px;color:#475569}
.filter-info span{color:#94a3b8}
.controls{display:flex;gap:14px;align-items:center;padding:10px 28px;background:#0f0f0f;border-bottom:1px solid #1a1a1a;flex-wrap:wrap}
.controls label{color:#64748b;font-size:11px;text-transform:uppercase;letter-spacing:.5px}
.controls select,.controls input{background:#1e293b;color:#e5e5e5;border:1px solid #334155;padding:6px 10px;border-radius:4px;font-family:inherit;font-size:12px;min-width:180px}
.controls select:focus,.controls input:focus{outline:none;border-color:#22d3ee}
.controls .count-tag{color:#22d3ee;font-weight:600}
.controls .clear-btn{background:#3b0764;color:#c084fc;border:none;padding:6px 12px;border-radius:4px;cursor:pointer;font-family:inherit;font-size:11px;font-weight:600}
.controls .clear-btn:hover{background:#581c87}
.table-wrap{padding:12px 28px 40px;overflow-x:auto}
table{width:100%;border-collapse:collapse}
th{text-align:left;padding:10px 12px;color:#64748b;font-weight:500;font-size:11px;text-transform:uppercase;letter-spacing:.5px;border-bottom:1px solid #1e293b;cursor:pointer;user-select:none;white-space:nowrap}
th:hover{color:#94a3b8}
th.sorted-asc::after{content:" \u25B2";color:#22d3ee}
th.sorted-desc::after{content:" \u25BC";color:#22d3ee}
td{padding:9px 12px;border-bottom:1px solid #141414;white-space:nowrap}
tr:hover td{background:#111827}
.sym a{color:#f1f5f9;font-weight:600;text-decoration:none}.sym a:hover{color:#22d3ee;text-decoration:underline}
.sector-cell{color:#94a3b8;font-size:11px;max-width:200px;overflow:hidden;text-overflow:ellipsis;cursor:pointer}
.sector-cell:hover{color:#22d3ee;text-decoration:underline}
.num{text-align:right;font-variant-numeric:tabular-nums}
.pos{color:#4ade80}.neg{color:#f87171}
.tag{display:inline-block;padding:2px 7px;border-radius:3px;font-size:10px;font-weight:600}
.tag-near{background:#164e63;color:#22d3ee}.tag-below{background:#3b0764;color:#c084fc}.tag-above{background:#14532d;color:#4ade80}
.touch-tag{display:inline-block;padding:2px 7px;border-radius:3px;font-size:10px;font-weight:600;background:#1e1b4b;color:#a78bfa}
.empty{text-align:center;padding:60px;color:#475569}
.empty h3{font-size:16px;margin-bottom:8px;color:#64748b}
.footer{padding:12px 28px;color:#334155;font-size:10px;text-align:center;border-top:1px solid #1a1a1a}
</style>
</head>
<body>
<div class="header">
  <h1>&#9889; EMA9 PULLBACK SCANNER</h1>
  <div class="sub">NSE Stocks &middot; Green candle LOW touching EMA9 &middot; LTP +0.5% to +4% &middot; LTP &lt; EMA9+6% &middot; Port 5037</div>
</div>
<div class="toolbar">
  <button class="btn btn-scan" id="btnScan" onclick="startScan()">&#9654; SCAN NOW</button>
  <button class="btn btn-export" onclick="location.href='/export'">&#11015; EXCEL</button>
  <div class="progress-bar"><div class="progress-outer"><div class="progress-inner" id="progBar" style="width:0%"></div><div class="progress-text" id="progText">Ready</div></div></div>
</div>
<div class="filter-info">
  Filters: <span>Gap 4-10%</span> &middot; <span>EMA9 Slope -1.5 to 20%</span> &middot;
  <span>EMA21 Slope 2-15%</span> &middot; <span>LOW &plusmn;2% of EMA9 (last 5d)</span> &middot;
  <span>Green candle</span> &middot; <span>LTP +0.5% to +4% vs prev close</span> &middot;
  <span>LTP &lt; EMA9+6%</span>
</div>
<div class="controls">
  <label>Sector:</label>
  <select id="sectorFilter" onchange="renderTable()"><option value="">All sectors</option></select>
  <label>Search:</label>
  <input id="symSearch" type="text" placeholder="Filter symbol..." oninput="renderTable()">
  <button class="clear-btn" onclick="clearFilters()">CLEAR</button>
  <span style="color:#64748b;font-size:11px;margin-left:auto">
    Showing <span class="count-tag" id="visibleCount">0</span> of <span id="totalCount">0</span>
    &middot; Last scan: <span class="count-tag" id="lastScan">&mdash;</span>
  </span>
</div>
<div class="table-wrap">
  <table id="resultsTable">
    <thead><tr>
      <th data-col="0">#</th><th data-col="1">Symbol</th><th data-col="2">Sector</th>
      <th data-col="3" class="num">LTP</th><th data-col="4" class="num">EMA9</th>
      <th data-col="5" class="num">EMA21</th><th data-col="6" class="num">Gap%</th>
      <th data-col="7" class="num">EMA9 Slope</th><th data-col="8" class="num">EMA21 Slope</th>
      <th data-col="9" class="num">Proximity</th><th data-col="10" class="num">Day Chg%</th>
      <th data-col="11">Touch</th>
    </tr></thead>
    <tbody id="tbody"></tbody>
  </table>
  <div class="empty" id="emptyMsg"><h3>No results yet</h3><p>Click SCAN NOW to find stocks pulling back to the 9 EMA</p></div>
</div>
<div class="footer">EMA9 Pullback Scanner &middot; LOW &plusmn;2% touch &middot; LTP +0.5% to +4% &middot; LTP &lt; EMA9+6% &middot; Sector filter &middot; Port 5037</div>
<script>
let tableData=[],sortCol=6,sortDir='asc';
function startScan(){const b=document.getElementById('btnScan');b.disabled=true;b.textContent='SCANNING...';fetch('/scan',{method:'POST'}).then(()=>listenProgress())}
function listenProgress(){const es=new EventSource('/progress');es.onmessage=e=>{const d=JSON.parse(e.data);if(d.done){es.close();loadResults();return}const p=d.total?Math.round(d.current/d.total*100):0;document.getElementById('progBar').style.width=p+'%';document.getElementById('progText').textContent=d.phase+' '+(d.total?d.current+'/'+d.total+' '+d.symbol:'')};es.onerror=()=>{es.close();loadResults()}}
function loadResults(){fetch('/results').then(r=>r.json()).then(data=>{tableData=data;document.getElementById('btnScan').disabled=false;document.getElementById('btnScan').textContent='\u25B6 SCAN NOW';document.getElementById('totalCount').textContent=data.length;if(data.length)document.getElementById('lastScan').textContent=data[0].scan_date;populateSectorDropdown();renderTable()})}
function populateSectorDropdown(){const sel=document.getElementById('sectorFilter');const cur=sel.value;const sec={};tableData.forEach(r=>{const s=r.sector||'(no sector)';sec[s]=(sec[s]||0)+1});const sorted=Object.keys(sec).sort();sel.innerHTML='<option value="">All sectors ('+tableData.length+')</option>';sorted.forEach(s=>{const o=document.createElement('option');o.value=s;o.textContent=s+' ('+sec[s]+')';sel.appendChild(o)});sel.value=cur}
function clearFilters(){document.getElementById('sectorFilter').value='';document.getElementById('symSearch').value='';renderTable()}
function filterBySector(s){document.getElementById('sectorFilter').value=s||'(no sector)';renderTable()}
function renderTable(){const tb=document.getElementById('tbody'),em=document.getElementById('emptyMsg');const sf=document.getElementById('sectorFilter').value;const ss=document.getElementById('symSearch').value.trim().toLowerCase();let f=tableData;if(sf)f=f.filter(r=>(r.sector||'(no sector)')===sf);if(ss)f=f.filter(r=>r.symbol.toLowerCase().includes(ss));document.getElementById('visibleCount').textContent=f.length;if(!f.length){tb.innerHTML='';em.style.display='block';em.querySelector('h3').textContent=tableData.length?'No matches':'No results yet';return}em.style.display='none';const keys=['','symbol','sector','ltp','ema9','ema21','gap_pct','ema9_slope','ema21_slope','proximity_pct','day_change_pct','touch_day'];const k=keys[sortCol];if(k){f.sort((a,b)=>{let va=a[k]||'',vb=b[k]||'';if(typeof va==='string'){va=va.toLowerCase();vb=vb.toLowerCase()}if(va<vb)return sortDir==='asc'?-1:1;if(va>vb)return sortDir==='asc'?1:-1;return 0})}document.querySelectorAll('th').forEach(th=>{th.classList.remove('sorted-asc','sorted-desc');if(parseInt(th.dataset.col)===sortCol)th.classList.add('sorted-'+sortDir)});let h='';f.forEach((r,i)=>{const cc=r.day_change_pct>=0?'pos':'neg';const pc=Math.abs(r.proximity_pct)<0.5?'tag-near':r.proximity_pct<0?'tag-below':'tag-above';const pl=Math.abs(r.proximity_pct)<0.5?'NEAR':r.proximity_pct<0?'BELOW':'ABOVE';const u='https://www.tradingview.com/chart/?symbol=NSE%3A'+r.symbol;const sc=(r.sector||'').replace(/'/g,"\\'");h+='<tr><td style="color:#475569">'+(i+1)+'</td><td class="sym"><a href="'+u+'" target="_blank">'+r.symbol+'</a></td><td class="sector-cell" onclick="filterBySector(\''+sc+'\')" title="Click to filter">'+(r.sector||'')+'</td><td class="num">\u20B9'+r.ltp.toLocaleString('en-IN',{minimumFractionDigits:2})+'</td><td class="num" style="color:#22d3ee">'+r.ema9.toFixed(2)+'</td><td class="num" style="color:#a78bfa">'+r.ema21.toFixed(2)+'</td><td class="num">'+r.gap_pct.toFixed(2)+'%</td><td class="num">'+r.ema9_slope.toFixed(2)+'%</td><td class="num">'+r.ema21_slope.toFixed(2)+'%</td><td class="num"><span class="tag '+pc+'">'+pl+' '+r.proximity_pct.toFixed(2)+'%</span></td><td class="num '+cc+'">+'+r.day_change_pct.toFixed(2)+'%</td><td><span class="touch-tag">'+(r.touch_day||'')+'</span></td></tr>'});tb.innerHTML=h}
document.querySelectorAll('th').forEach(th=>{th.addEventListener('click',()=>{const c=parseInt(th.dataset.col);if(c===sortCol)sortDir=sortDir==='asc'?'desc':'asc';else{sortCol=c;sortDir='asc'}renderTable()})});
loadResults();
</script>
</body></html>
"""

if __name__ == "__main__":
    import webbrowser
    print(f"\n  EMA9 Pullback Scanner | Port {PORT}")
    print(f"  Filters: Gap {GAP_PCT_MIN}-{GAP_PCT_MAX}% | EMA9 Slope {EMA9_SLOPE5_MIN}-{EMA9_SLOPE5_MAX}%")
    print(f"  EMA21 Slope {EMA21_SLOPE5_MIN}-{EMA21_SLOPE5_MAX}%")
    print(f"  EMA9 Touch: LOW within -{TOUCH_BELOW*100}% to +{TOUCH_ABOVE*100}% (last {TOUCH_LOOKBACK} days)")
    print(f"  Green candle on touch day")
    print(f"  LTP vs Prev Close: +{INTRADAY_GAIN_MIN}% to +{INTRADAY_GAIN_MAX}%")
    print(f"  LTP < EMA9 + {LTP_EMA9_MAX}%\n")
    run_scan(console=True)
    print(f"  Opening dashboard at http://127.0.0.1:{PORT} ...\n")
    webbrowser.open(f"http://127.0.0.1:{PORT}")
    app.run(host="0.0.0.0", port=PORT, debug=False)
'''

target = os.path.join(FOLDER, "app.py")
with open(target, "w", encoding="utf-8") as f:
    f.write(APP)

# ── FINAL VERIFY ──
app_verify = open(target, "r", encoding="utf-8").read()
print(f"\n  FINAL BUILD applied!")
print(f"  Verification:")
print(f"    LTP_EMA9_MAX in config.py: {'LTP_EMA9_MAX' in verify}")
print(f"    LTP_EMA9_MAX in app.py:    {'LTP_EMA9_MAX' in app_verify}")
print(f"\n  Filters:")
print(f"    1. EMA9 > EMA21")
print(f"    2. Gap% 4-10%")
print(f"    3. EMA9 Slope -1.50% to 20%")
print(f"    4. EMA21 Slope 2% to 15%")
print(f"    5. LOW +/-2% of EMA9 + green candle (last 5 days)")
print(f"    6. LTP vs Prev Close: +0.5% to +4%")
print(f"    7. LTP < EMA9 x 1.06")
print(f"    8. Sector from Screener.in + sector filter in UI")
print(f"\n  Run: python app.py\n")
