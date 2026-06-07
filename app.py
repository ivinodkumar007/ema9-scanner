# ============================================
# EMA9 Pullback Scanner | Port 5037
# ============================================
# Filters:
#   1. EMA9 > EMA21
#   2. Gap% 4-10%
#   3. EMA9 Slope -1.5 to 20%
#   4. EMA21 Slope 2-15%
#   5. Candle LOW within +/-2% of EMA9 + green candle (last 5 days)
#   6. LTP vs Prev Close: +0.5% to +4%
#   7. LTP < EMA9 x 1.06 (max 6% above EMA9)
#   Sector from Screener.in (cached). On-demand only.
# ============================================

import os, sys, json, time, threading, sqlite3, smtplib, io, re, subprocess, platform
from datetime import datetime, timedelta, date
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

import pandas as pd
import requests as http_requests
from flask import Flask, render_template_string, jsonify, Response, send_file, redirect, request

from config import *
from auth import get_kite

# Import SQLAlchemy for PostgreSQL support
if DB_TYPE == 'postgresql':
    from sqlalchemy import create_engine, text
    db_engine = create_engine(DB_PATH)
    # Add connection pooling settings
    db_engine.pool._recycle = 300  # Recycle connections every 5 min

app = Flask(__name__)

# Directory for chunk files
CHUNK_DIR = os.path.join(DATA_DIR if DB_TYPE == 'sqlite' else '/tmp', 'scan_chunks')
os.makedirs(CHUNK_DIR, exist_ok=True)

scan_progress = {"running": False, "current": 0, "total": 0, "symbol": "", "phase": ""}
scan_results_cache = []
last_scan_time = ""


def get_db_connection():
    """Get database connection (works with both SQLite and PostgreSQL)."""
    if DB_TYPE == 'postgresql':
        return db_engine.connect()
    else:
        return sqlite3.connect(DB_PATH)

def init_db():
    """Initialize database tables."""
    if DB_TYPE == 'postgresql':
        # PostgreSQL initialization
        with db_engine.connect() as conn:
            conn.execute(text("""CREATE TABLE IF NOT EXISTS scan_results (
                id SERIAL PRIMARY KEY,
                scan_date TEXT, symbol TEXT, ltp REAL, ema9 REAL, ema21 REAL,
                gap_pct REAL, ema9_slope REAL, ema21_slope REAL,
                proximity_pct REAL, day_change_pct REAL, sector TEXT DEFAULT '',
                touch_day TEXT DEFAULT '',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )"""))
            conn.execute(text("""CREATE TABLE IF NOT EXISTS scan_log (
                id SERIAL PRIMARY KEY,
                scan_date TEXT, total_stocks INTEGER, passed INTEGER, duration_sec REAL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )"""))
            conn.execute(text("""CREATE TABLE IF NOT EXISTS sector_cache (
                symbol TEXT PRIMARY KEY, sector TEXT, updated_at TEXT
            )"""))
            conn.commit()
    else:
        # SQLite initialization
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
        for col in ["sector TEXT DEFAULT ''", "touch_day TEXT DEFAULT '']"]:
            try:
                c.execute(f"ALTER TABLE scan_results ADD COLUMN {col}")
            except Exception:
                pass
        conn.commit()
        conn.close()

init_db()


def get_sector(symbol):
    """Get sector for a symbol (with caching)."""
    if DB_TYPE == 'postgresql':
        with db_engine.connect() as conn:
            result = conn.execute(text("SELECT sector FROM sector_cache WHERE symbol = :symbol"), {"symbol": symbol})
            row = result.fetchone()
            if row and row[0]:
                return row[0]
    else:
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        c.execute("SELECT sector FROM sector_cache WHERE symbol = ?", (symbol,))
        row = c.fetchone()
        if row and row[0]:
            conn.close()
            return row[0]
        conn.close()
    
    sector = ""
    try:
        url = f"https://www.screener.in/company/{symbol}/"
        headers = {"User-Agent": "Mozilla/5.0"}
        r = http_requests.get(url, headers=headers, timeout=8)
        if r.status_code == 200:
            m = re.search(r'icon-industry.*?<a[^>]*>([^<]+)', r.text, re.S)
            if m:
                import html as html_mod
                sector = html_mod.unescape(m.group(1).strip())
    except Exception:
        pass
    
    if sector:
        if DB_TYPE == 'postgresql':
            with db_engine.connect() as conn:
                conn.execute(text(
                    "INSERT INTO sector_cache (symbol, sector, updated_at) VALUES (:symbol, :sector, :updated_at) "
                    "ON CONFLICT (symbol) DO UPDATE SET sector = :sector, updated_at = :updated_at"
                ), {
                    "symbol": symbol,
                    "sector": sector,
                    "updated_at": datetime.now().strftime("%Y-%m-%d")
                })
                conn.commit()
        else:
            conn = sqlite3.connect(DB_PATH)
            c = conn.cursor()
            c.execute("INSERT OR REPLACE INTO sector_cache (symbol, sector, updated_at) VALUES (?,?,?)",
                      (symbol, sector, datetime.now().strftime("%Y-%m-%d")))
            conn.commit()
            conn.close()
    
    return sector


def load_symbols():
    if not os.path.exists(NSE_STOCKS_FILE):
        print(f"  ERROR: {NSE_STOCKS_FILE} not found")
        return []
    try:
        if NSE_STOCKS_FILE.endswith(".csv"):
            df = pd.read_csv(NSE_STOCKS_FILE)
            col = "SYMBOL" if "SYMBOL" in df.columns else df.columns[0]
            # Also load ISIN if available
            isin_col = None
            for c in df.columns:
                if 'ISIN' in c.upper():
                    isin_col = c
                    break
            
            symbols = []
            for _, row in df.iterrows():
                sym = str(row[col]).strip()
                isin = str(row[isin_col]).strip() if isin_col and pd.notna(row.get(isin_col)) else ""
                if sym and sym != "nan":
                    symbols.append({"symbol": sym, "isin": isin})
            
            print(f"  Loaded {len(symbols)} symbols (with ISIN: {sum(1 for s in symbols if s['isin'])})")
            return symbols
        else:
            df = pd.read_excel(NSE_STOCKS_FILE)
            col = df.columns[0]
            syms = df[col].dropna().astype(str).str.strip().tolist()
            return [{"symbol": s, "isin": ""} for s in syms if s and s != "nan"]
    except Exception as e:
        print(f"  ERROR loading symbols: {e}")
        return []


def calc_ema(prices, period):
    if len(prices) < period:
        return []
    k = 2 / (period + 1)
    ema = [sum(prices[:period]) / period]
    for p in prices[period:]:
        ema.append(p * k + ema[-1] * (1 - k))
    return ema


def run_scan(console=False):
    global scan_progress, scan_results_cache, last_scan_time

    if scan_progress["running"]:
        return

    scan_progress = {"running": True, "current": 0, "total": 0, "symbol": "", "phase": "Authenticating..."}

    if console:
        print("\n" + "="*70)
        print("  EMA9 PULLBACK SCANNER")
        print("="*70)
        print("  Authenticating with Upstox...")

    kite = get_kite()
    if not kite:
        scan_progress = {"running": False, "current": 0, "total": 0, "symbol": "", "phase": "Auth failed"}
        if console:
            print("  X Auth failed!")
        return

    if console:
        print("  OK Authenticated\n")

    symbols = load_symbols()
    if not symbols:
        scan_progress = {"running": False, "current": 0, "total": 0, "symbol": "", "phase": "No symbols"}
        return

    total = len(symbols)
    scan_progress["total"] = total
    today = date.today()
    from_date = today - timedelta(days=CANDLE_DAYS)
    start_time = time.time()

    # ================================================================
    # PASS 1: EMA Gate + LOW Touch + Green Candle
    # ================================================================
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

    pass1_results = []

    for idx, sym_info in enumerate(symbols):
        sym = sym_info["symbol"] if isinstance(sym_info, dict) else sym_info
        isin = sym_info.get("isin", "") if isinstance(sym_info, dict) else ""
        scan_progress["current"] = idx + 1
        scan_progress["symbol"] = sym

        if console and (idx + 1) % 50 == 0:
            print(f"  [{idx+1}/{total}] Scanning {sym}... (hits: {len(pass1_results)})")

        try:
            # Get instrument token (used for Kite, Upstox handles it internally)
            token = _get_instrument_token(kite, sym)
            if not token:
                continue

            # Fetch historical candles
            # UpstoxClient accepts (symbol, from_date, to_date, interval)
            # Kite accepts (instrument_token, from_date, to_date, interval)
            if hasattr(kite, '_get_instrument_token'):
                # Upstox
                candles = kite.historical_data(
                    symbol=sym,
                    from_date=from_date,
                    to_date=today,
                    interval="day",
                    isin=isin
                )
            else:
                # Kite (legacy)
                candles = kite.historical_data(
                    instrument_token=token,
                    from_date=from_date,
                    to_date=today,
                    interval="day"
                )

            if not candles or len(candles) < 30:
                continue

            closes = [c["close"] for c in candles]
            opens  = [c["open"]  for c in candles]
            lows   = [c["low"]   for c in candles]

            ema9_all  = calc_ema(closes, 9)
            ema21_all = calc_ema(closes, 21)

            if not ema9_all or not ema21_all:
                continue

            offset = 21 - 9
            ema9  = ema9_all[offset:]
            ema21 = ema21_all[:]
            min_len = min(len(ema9), len(ema21))
            ema9  = ema9[-min_len:]
            ema21 = ema21[-min_len:]
            aligned_closes = closes[-min_len:]
            aligned_opens  = opens[-min_len:]
            aligned_lows   = lows[-min_len:]

            if len(ema9) < 6 or len(ema21) < 6:
                continue

            cur_ema9  = ema9[-1]
            cur_ema21 = ema21[-1]
            cur_close = aligned_closes[-1]
            prev_close = aligned_closes[-2] if len(aligned_closes) > 1 else cur_close

            # F1: EMA9 > EMA21
            if cur_ema9 <= cur_ema21:
                continue

            # F2: Gap %
            gap_pct = ((cur_ema9 - cur_ema21) / cur_ema21) * 100
            if gap_pct < GAP_PCT_MIN or gap_pct > GAP_PCT_MAX:
                continue

            # F3: EMA9 Slope
            ema9_slope = ((ema9[-1] - ema9[-6]) / ema9[-6]) * 100
            if ema9_slope < EMA9_SLOPE5_MIN or ema9_slope > EMA9_SLOPE5_MAX:
                continue

            # F4: EMA21 Slope
            ema21_slope = ((ema21[-1] - ema21[-6]) / ema21[-6]) * 100
            if ema21_slope < EMA21_SLOPE5_MIN or ema21_slope > EMA21_SLOPE5_MAX:
                continue

            # F5: EMA9 Touch — LOW within +/-2% of EMA9 + green candle
            touch_day = ""
            lookback = min(TOUCH_LOOKBACK, len(aligned_closes), len(ema9))
            for d in range(lookback):
                day_close = aligned_closes[-(d+1)]
                day_open  = aligned_opens[-(d+1)]
                day_low   = aligned_lows[-(d+1)]
                day_ema9  = ema9[-(d+1)]
                lower = day_ema9 * (1 - TOUCH_BELOW)
                upper = day_ema9 * (1 + TOUCH_ABOVE)
                if lower <= day_low <= upper and day_close > day_open:
                    touch_day = f"T-{d}" if d > 0 else "T-0"
                    break

            if not touch_day:
                continue

            pass1_results.append({
                "symbol": sym, "isin": isin, "ema9": cur_ema9, "ema21": cur_ema21,
                "gap_pct": gap_pct, "ema9_slope": ema9_slope,
                "ema21_slope": ema21_slope, "cur_close": cur_close,
                "prev_close": prev_close, "touch_day": touch_day,
            })

        except Exception:
            pass

        if (idx + 1) % 3 == 0:
            time.sleep(0.35)

    pass1_time = round(time.time() - start_time, 1)

    if console:
        print(f"\n  PASS 1 COMPLETE: {len(pass1_results)}/{total} passed ({pass1_time}s)")
        if pass1_results:
            print(f"  Passed: {', '.join(r['symbol'] for r in pass1_results[:20])}")
            if len(pass1_results) > 20:
                print(f"          ...and {len(pass1_results)-20} more")
        print()

    # ================================================================
    # PASS 2: LTP checks — day change +0.5% to +4% AND LTP < EMA9*1.06
    # ================================================================
    scan_progress["phase"] = "Pass 2: LTP checks"
    if console:
        print("-"*70)
        print(f"  PASS 2: LTP vs Prev Close +{INTRADAY_GAIN_MIN}% to +{INTRADAY_GAIN_MAX}%")
        print(f"          LTP < EMA9 + {LTP_EMA9_MAX}% ({len(pass1_results)} stocks)")
        print("-"*70)

    results = []
    BATCH_SIZE = 50  # Process 50 stocks per API call
    CHUNK_SIZE = 50  # Save chunk every 50 stocks
    
    # Load existing results for today (in case of resume)
    scan_date = today.strftime("%Y-%m-%d")
    if DB_TYPE == 'postgresql':
        try:
            with db_engine.connect() as conn:
                result = conn.execute(text(
                    "SELECT symbol, ltp, ema9, ema21, gap_pct, ema9_slope, ema21_slope, "
                    "proximity_pct, day_change_pct, sector, touch_day "
                    "FROM scan_results WHERE scan_date = :scan_date"
                ), {"scan_date": scan_date})
                for row in result.fetchall():
                    results.append({
                        "symbol": row[0], "ltp": row[1], "ema9": row[2], "ema21": row[3],
                        "gap_pct": row[4], "ema9_slope": row[5], "ema21_slope": row[6],
                        "proximity_pct": row[7], "day_change_pct": row[8],
                        "sector": row[9], "touch_day": row[10]
                    })
                if results:
                    print(f"  ✓ Resuming scan with {len(results)} existing results")
        except Exception as e:
            print(f"  ⚠ Could not load existing results: {e}")

    for idx, p in enumerate(pass1_results):
        # Skip if already processed (for resume)
        if any(r["symbol"] == p["symbol"] for r in results):
            continue
        sym = p["symbol"]
        isin = p.get("isin", "")
        instrument = f"NSE:{sym}"
        scan_progress["current"] = idx + 1
        scan_progress["total"] = len(pass1_results)
        scan_progress["symbol"] = sym

        try:
            ohlc_data = kite.ohlc(sym, isin=isin)
            # Handle both Kite and Upstox response formats
            if isinstance(ohlc_data, dict) and "last_price" in ohlc_data:
                # Upstox format
                ltp = ohlc_data["last_price"]
                prev_cl = ohlc_data["ohlc"]["close"]
            elif isinstance(ohlc_data, dict) and instrument in ohlc_data:
                # Kite format
                ltp = ohlc_data[instrument]["last_price"]
                prev_cl = ohlc_data[instrument]["ohlc"]["close"]
            else:
                raise ValueError("Unknown OHLC format")
        except Exception:
            ltp = p["cur_close"]; prev_cl = p["prev_close"]

        day_change = ((ltp - prev_cl) / prev_cl) * 100 if p["prev_close"] else 0
        proximity_pct = ((ltp - p["ema9"]) / p["ema9"]) * 100
        ltp_cap = p["ema9"] * (1 + LTP_EMA9_MAX / 100)

        # F6: LTP vs Prev Close: +0.5% to +4%
        # F7: LTP < EMA9 * 1.06
        f6_pass = INTRADAY_GAIN_MIN <= day_change <= INTRADAY_GAIN_MAX
        f7_pass = ltp < ltp_cap

        if f6_pass and f7_pass:
            results.append({
                "symbol": sym, "ltp": round(ltp, 2),
                "ema9": round(p["ema9"], 2), "ema21": round(p["ema21"], 2),
                "gap_pct": round(p["gap_pct"], 2),
                "ema9_slope": round(p["ema9_slope"], 2),
                "ema21_slope": round(p["ema21_slope"], 2),
                "proximity_pct": round(proximity_pct, 2),
                "day_change_pct": round(day_change, 2),
                "sector": "", "touch_day": p["touch_day"],
            })
            status = ">> HIT"
        else:
            reasons = []
            if not f6_pass:
                reasons.append(f"chg {day_change:+.2f}%")
            if not f7_pass:
                reasons.append(f"LTP {ltp:.0f} > cap {ltp_cap:.0f}")
            status = f"X ({', '.join(reasons)})"

        if console:
            print(f"  [{idx+1}/{len(pass1_results)}] {sym:20s} LTP={ltp:>10.2f}  Chg={day_change:>+6.2f}%  Prox={proximity_pct:>+6.2f}%  {status}")

        if (idx + 1) % 5 == 0:
            time.sleep(0.2)
        
        # Save to chunk files every 50 stocks (avoids timeout)
        if (idx + 1) % CHUNK_SIZE == 0:
            chunk_file = os.path.join(CHUNK_DIR, f"chunk_{scan_date}_{idx+1}.json")
            try:
                # Save current results to chunk file
                with open(chunk_file, 'w') as f:
                    json.dump(results, f)
                if console:
                    print(f"  ✓ Saved chunk: {len(results)} results (stocks 1-{idx+1})")
                
                # Break for 1 second to reset connection
                time.sleep(1)
                if console:
                    print(f"  ⏱️  1-second break (connection reset)")
            except Exception as e:
                if console:
                    print(f"  ⚠ Chunk save failed: {e}")

    # ================================================================
    # PASS 3: Sector lookup from Screener.in
    # ================================================================
    if results:
        scan_progress["phase"] = "Pass 3: Sector lookup"
        if console:
            print(f"\n  PASS 3: Sector lookup for {len(results)} stocks...")
        for idx, r in enumerate(results):
            scan_progress["symbol"] = r["symbol"]
            scan_progress["current"] = idx + 1
            scan_progress["total"] = len(results)
            sector = get_sector(r["symbol"])
            r["sector"] = sector
            if console:
                print(f"  [{idx+1}/{len(results)}] {r['symbol']:20s} -> {sector or '(unknown)'}")
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

    # Save all results to database (consolidate chunks)
    if DB_TYPE == 'postgresql':
        try:
            with db_engine.connect() as conn:
                conn.execute(text("DELETE FROM scan_results WHERE scan_date = :scan_date"), 
                           {"scan_date": scan_date})
                for r in results:
                    conn.execute(text("""INSERT INTO scan_results
                        (scan_date, symbol, ltp, ema9, ema21, gap_pct, ema9_slope, ema21_slope,
                         proximity_pct, day_change_pct, sector, touch_day)
                        VALUES (:scan_date, :symbol, :ltp, :ema9, :ema21, :gap_pct, :ema9_slope, :ema21_slope,
                                :proximity_pct, :day_change_pct, :sector, :touch_day)"""), {
                        "scan_date": scan_date,
                        "symbol": r["symbol"], "ltp": r["ltp"], "ema9": r["ema9"],
                        "ema21": r["ema21"], "gap_pct": r["gap_pct"],
                        "ema9_slope": r["ema9_slope"], "ema21_slope": r["ema21_slope"],
                        "proximity_pct": r["proximity_pct"], "day_change_pct": r["day_change_pct"],
                        "sector": r["sector"], "touch_day": r["touch_day"]
                    })
                conn.commit()
                if console:
                    print(f"  ✓ Saved {len(results)} results to PostgreSQL")
        except Exception as e:
            if console:
                print(f"  ⚠ DB save failed: {e}")
    
    # Clean up chunk files
    try:
        for f in os.listdir(CHUNK_DIR):
            if f.startswith(f"chunk_{scan_date}_"):
                os.remove(os.path.join(CHUNK_DIR, f))
        if console:
            print(f"  ✓ Cleaned up chunk files")
    except Exception as e:
        if console:
            print(f"  ⚠ Cleanup failed: {e}")

    # Save scan log (results already saved in batches)
    if DB_TYPE == 'postgresql':
        with db_engine.connect() as conn:
            conn.execute(text("""INSERT INTO scan_log (scan_date, total_stocks, passed, duration_sec) 
                                VALUES (:scan_date, :total_stocks, :passed, :duration_sec)"""), {
                "scan_date": scan_date,
                "total_stocks": len(symbols),
                "passed": len(results),
                "duration_sec": elapsed
            })
            conn.commit()
    else:
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        c.execute("INSERT INTO scan_log (scan_date, total_stocks, passed, duration_sec) VALUES (?,?,?,?)",
                  (scan_date, len(symbols), len(results), elapsed))
        conn.commit()
        conn.close()

    scan_results_cache = results
    last_scan_time = datetime.now().strftime("%d-%b-%Y %I:%M %p")

    if results and GMAIL_SENDER and GMAIL_APP_PASSWORD:
        send_gmail(results, scan_date)

    scan_progress = {"running": False, "current": len(pass1_results), "total": len(pass1_results),
                     "symbol": "Done", "phase": f"Complete: {len(results)} stocks found in {elapsed}s"}


_instrument_cache = {}

def _get_instrument_token(client, symbol):
    """Get instrument token from client's cache (works with both Kite and Upstox)."""
    global _instrument_cache
    if not _instrument_cache:
        # For UpstoxClient, use internal instrument lookup
        if hasattr(client, '_get_instrument_token'):
            # Upstox - cache the instruments
            instruments = client.instruments("NSE")
            for inst in instruments:
                _instrument_cache[inst.get("tradingsymbol")] = inst.get("instrument_token")
        else:
            # Kite (legacy)
            instruments = client.instruments("NSE")
            for inst in instruments:
                _instrument_cache[inst["tradingsymbol"]] = inst["instrument_token"]
    return _instrument_cache.get(symbol)


def send_gmail(results, scan_date):
    try:
        msg = MIMEMultipart("alternative")
        msg["Subject"] = f"EMA9 Pullback: {len(results)} stocks - {scan_date}"
        msg["From"] = GMAIL_SENDER
        msg["To"] = GMAIL_RECIPIENT
        rows_html = ""
        for r in results:
            color = "#4ade80" if r["day_change_pct"] >= 0 else "#f87171"
            rows_html += f"""<tr>
                <td style="padding:6px 10px;border-bottom:1px solid #333"><a href="https://www.tradingview.com/chart/?symbol=NSE%3A{r['symbol']}" style="color:#22d3ee">{r['symbol']}</a></td>
                <td style="padding:6px 10px;border-bottom:1px solid #333">{r.get('sector','')}</td>
                <td style="padding:6px 10px;border-bottom:1px solid #333;text-align:right">{r['ltp']:,.2f}</td>
                <td style="padding:6px 10px;border-bottom:1px solid #333;text-align:right">{r['gap_pct']:.2f}%</td>
                <td style="padding:6px 10px;border-bottom:1px solid #333;text-align:right;color:{color}">{r['day_change_pct']:+.2f}%</td>
                <td style="padding:6px 10px;border-bottom:1px solid #333;text-align:right">{r['proximity_pct']:+.2f}%</td>
                <td style="padding:6px 10px;border-bottom:1px solid #333">{r.get('touch_day','')}</td>
            </tr>"""
        html = f"""<html><body style="background:#111;color:#e5e5e5;font-family:monospace;padding:20px">
        <h2 style="color:#22d3ee">EMA9 Pullback: {scan_date}</h2>
        <p>{len(results)} stocks | LTP +{INTRADAY_GAIN_MIN}% to +{INTRADAY_GAIN_MAX}% today | LTP &lt; EMA9+{LTP_EMA9_MAX}%</p>
        <table style="border-collapse:collapse;width:100%">
        <tr style="color:#a3a3a3"><th style="padding:8px 10px;text-align:left">Symbol</th>
        <th style="text-align:left;padding:8px 10px">Sector</th>
        <th style="text-align:right;padding:8px 10px">LTP</th>
        <th style="text-align:right;padding:8px 10px">Gap%</th>
        <th style="text-align:right;padding:8px 10px">Chg%</th>
        <th style="text-align:right;padding:8px 10px">Prox%</th>
        <th style="text-align:left;padding:8px 10px">Touch</th></tr>
        {rows_html}</table></body></html>"""
        msg.attach(MIMEText(html, "html"))
        with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
            server.login(GMAIL_SENDER, GMAIL_APP_PASSWORD)
            server.sendmail(GMAIL_SENDER, GMAIL_RECIPIENT, msg.as_string())
        print(f"  Gmail sent: {len(results)} stocks")
    except Exception as e:
        print(f"  Gmail error: {e}")


@app.route("/progress")
def progress():
    def stream():
        count = 0
        while count < 1200:  # Max 10 minutes (1200 * 0.5s)
            data = json.dumps(scan_progress)
            yield f"data: {data}\n\n"
            if not scan_progress["running"] and scan_progress["phase"].startswith("Complete"):
                yield f"data: {json.dumps({'done': True})}\n\n"
                break
            count += 1
            time.sleep(0.5)
    return Response(stream(), mimetype="text/event-stream")


@app.route("/health")
def health():
    """Health check endpoint for Render."""
    return jsonify({"status": "healthy", "timestamp": datetime.now().isoformat()})


@app.route("/scan", methods=["POST"])
def trigger_scan():
    """Start full scan (legacy - kept for compatibility)."""
    if scan_progress["running"]:
        return jsonify({"status": "already_running"})
    
    # Use non-daemon thread to prevent Render from killing it
    t = threading.Thread(target=run_scan, args=(False,), daemon=False)
    t.start()
    return jsonify({"status": "started"})


@app.route("/scan-chunk", methods=["POST"])
def scan_chunk():
    """Scan next 50 stocks with FULL logic (manual chunk-by-chunk for Render)."""
    try:
        data = request.json if request.is_json else {}
        start_idx = data.get('start_idx', 0)
        chunk_size = 50
        
        symbols = load_symbols()
        if not symbols:
            return jsonify({"error": "No symbols loaded"}), 400
        
        kite = get_kite()
        if not kite:
            return jsonify({"error": "Authentication failed"}), 400
        
        # Pre-load instrument cache once (saves time per stock)
        if hasattr(kite, 'instruments'):
            kite.instruments("NSE")
        
        end_idx = min(start_idx + chunk_size, len(symbols))
        chunk_symbols = symbols[start_idx:end_idx]
        
        today = date.today()
        from_date = today - timedelta(days=CANDLE_DAYS)
        scan_date = today.strftime("%Y-%m-%d")
        
        # Clear old results only on the FIRST chunk of a new scan
        if start_idx == 0 and DB_TYPE == 'postgresql':
            try:
                with db_engine.connect() as conn:
                    conn.execute(text("DELETE FROM scan_results WHERE scan_date = :scan_date"), {"scan_date": scan_date})
                    conn.commit()
                    print(f"  Cleared previous results for {scan_date}")
            except Exception as e:
                print(f"  Clear error: {e}")
        
        scan_progress["running"] = True
        scan_progress["phase"] = f"Scanning stocks {start_idx+1}-{end_idx}"
        scan_progress["current"] = start_idx
        scan_progress["total"] = len(symbols)
        
        chunk_results = []
        pass1_count = 0
        error_count = 0
        skip_reasons = {"no_token": 0, "no_candles": 0, "ema_len": 0, "ema9_below_ema21": 0,
                       "gap": 0, "ema9_slope": 0, "ema21_slope": 0, "no_touch": 0,
                       "day_change": 0, "ltp_cap": 0, "error": 0}
        
        for idx, sym_info in enumerate(chunk_symbols):
            actual_idx = start_idx + idx
            sym = sym_info["symbol"] if isinstance(sym_info, dict) else sym_info
            isin = sym_info.get("isin", "") if isinstance(sym_info, dict) else ""
            scan_progress["current"] = actual_idx + 1
            scan_progress["symbol"] = sym
            
            try:
                # UpstoxClient: use ISIN if available for exact instrument lookup
                is_upstox = hasattr(kite, '_get_instrument_token')
                
                if is_upstox:
                    candles = kite.historical_data(symbol=sym, from_date=from_date, to_date=today, interval="day", isin=isin)
                else:
                    token = _get_instrument_token(kite, sym)
                    if not token:
                        skip_reasons["no_token"] += 1
                        continue
                    candles = kite.historical_data(instrument_token=token, from_date=from_date, to_date=today, interval="day")
                
                if not candles or len(candles) < 30:
                    skip_reasons["no_candles"] += 1
                    continue
                
                closes = [c["close"] for c in candles]
                opens  = [c["open"]  for c in candles]
                highs  = [c["high"]  for c in candles]
                lows   = [c["low"]   for c in candles]
                
                ema9_all  = calc_ema(closes, 9)
                ema21_all = calc_ema(closes, 21)
                if not ema9_all or not ema21_all:
                    continue
                
                offset = 21 - 9
                ema9  = ema9_all[offset:]
                ema21 = ema21_all[:]
                min_len = min(len(ema9), len(ema21))
                ema9  = ema9[-min_len:]
                ema21 = ema21[-min_len:]
                aligned_closes = closes[-min_len:]
                aligned_opens  = opens[-min_len:]
                aligned_highs  = highs[-min_len:]
                aligned_lows   = lows[-min_len:]
                
                if len(ema9) < 6 or len(ema21) < 6:
                    skip_reasons["ema_len"] += 1
                    continue
                
                cur_ema9  = ema9[-1]
                cur_ema21 = ema21[-1]
                cur_close = aligned_closes[-1]
                prev_close = aligned_closes[-2] if len(aligned_closes) > 1 else cur_close
                
                # F1: EMA9 > EMA21
                if cur_ema9 <= cur_ema21:
                    skip_reasons["ema9_below_ema21"] += 1
                    continue
                
                # F2: Gap %
                gap_pct = ((cur_ema9 - cur_ema21) / cur_ema21) * 100
                if gap_pct < GAP_PCT_MIN or gap_pct > GAP_PCT_MAX:
                    skip_reasons["gap"] += 1
                    continue
                
                # F3: EMA9 Slope
                ema9_slope = ((ema9[-1] - ema9[-6]) / ema9[-6]) * 100
                if ema9_slope < EMA9_SLOPE5_MIN or ema9_slope > EMA9_SLOPE5_MAX:
                    skip_reasons["ema9_slope"] += 1
                    continue
                
                # F4: EMA21 Slope
                ema21_slope = ((ema21[-1] - ema21[-6]) / ema21[-6]) * 100
                if ema21_slope < EMA21_SLOPE5_MIN or ema21_slope > EMA21_SLOPE5_MAX:
                    skip_reasons["ema21_slope"] += 1
                    continue
                
                # F5: EMA9 Touch
                touch_day = ""
                lookback = min(TOUCH_LOOKBACK, len(aligned_closes), len(ema9))
                for d in range(lookback):
                    day_close = aligned_closes[-(d+1)]
                    day_open  = aligned_opens[-(d+1)]
                    day_low   = aligned_lows[-(d+1)]
                    day_ema9  = ema9[-(d+1)]
                    lower = day_ema9 * (1 - TOUCH_BELOW)
                    upper = day_ema9 * (1 + TOUCH_ABOVE)
                    if lower <= day_low <= upper and day_close > day_open:
                        touch_day = f"T-{d}" if d > 0 else "T-0"
                        break
                
                if not touch_day:
                    skip_reasons["no_touch"] += 1
                    continue
                
                pass1_count += 1
                
                # PASS 2: LTP checks - use OHLC API for live/last-trading-day prices
                ltp = 0
                prev_close = 0
                try:
                    ohlc_data = kite.ohlc(sym, isin=isin)
                    if isinstance(ohlc_data, dict) and "last_price" in ohlc_data:
                        ltp = ohlc_data["last_price"]
                        prev_close = ohlc_data["ohlc"]["close"]
                        # On weekends, OHLC might return 0 or stale data
                        if ltp <= 0 or prev_close <= 0:
                            ltp = cur_close
                            prev_close = aligned_closes[-2] if len(aligned_closes) > 1 else cur_close
                    else:
                        ltp = cur_close
                        prev_close = aligned_closes[-2] if len(aligned_closes) > 1 else cur_close
                except Exception as e:
                    print(f"  OHLC failed for {sym}: {e}")
                    ltp = cur_close
                    prev_close = aligned_closes[-2] if len(aligned_closes) > 1 else cur_close
                
                # Fallback: if still no valid prices, use historical data
                if ltp <= 0:
                    ltp = cur_close
                if prev_close <= 0:
                    prev_close = aligned_closes[-2] if len(aligned_closes) > 1 else cur_close
                
                day_change = ((ltp - prev_close) / prev_close) * 100 if prev_close else 0
                
                # Debug log first few stocks
                if idx < 5:
                    print(f"  [{start_idx+idx+1}] {sym}: LTP={ltp:.2f} prev={prev_close:.2f} chg={day_change:+.2f}% ema9={cur_ema9:.2f}")
                
                if day_change < INTRADAY_GAIN_MIN or day_change > INTRADAY_GAIN_MAX:
                    skip_reasons["day_change"] += 1
                    continue
                if ltp > cur_ema9 * (1 + LTP_EMA9_MAX / 100):
                    skip_reasons["ltp_cap"] += 1
                    continue
                
                proximity_pct = ((ltp - cur_ema9) / cur_ema9) * 100
                
                sector = get_sector(sym)
                
                chunk_results.append({
                    "symbol": sym, "isin": isin, "ltp": round(ltp, 2),
                    "ema9": round(cur_ema9, 2), "ema21": round(cur_ema21, 2),
                    "gap_pct": round(gap_pct, 2), "ema9_slope": round(ema9_slope, 2),
                    "ema21_slope": round(ema21_slope, 2),
                    "proximity_pct": round(proximity_pct, 2),
                    "day_change_pct": round(day_change, 2),
                    "sector": sector, "touch_day": touch_day
                })
                
            except Exception as e:
                skip_reasons["error"] += 1
                error_count += 1
                if error_count <= 3:
                    print(f"  ERROR on {sym}: {e}")
            
            if (idx + 1) % 5 == 0:
                time.sleep(0.1)
        
        # Log chunk summary
        print(f"\n  Chunk {start_idx+1}-{end_idx} Summary:")
        print(f"    Total: {len(chunk_symbols)} | Pass1: {pass1_count} | Final: {len(chunk_results)} | Errors: {error_count}")
        print(f"    Skip reasons: {skip_reasons}")
        print()
        
        # Save chunk results to DB (append, don't delete previous chunks)
        if DB_TYPE == 'postgresql':
            try:
                with db_engine.connect() as conn:
                    for r in chunk_results:
                        conn.execute(text("""INSERT INTO scan_results
                            (scan_date, symbol, ltp, ema9, ema21, gap_pct, ema9_slope, ema21_slope,
                             proximity_pct, day_change_pct, sector, touch_day)
                            VALUES (:scan_date, :symbol, :ltp, :ema9, :ema21, :gap_pct, :ema9_slope, :ema21_slope,
                                    :proximity_pct, :day_change_pct, :sector, :touch_day)"""), {
                            "scan_date": scan_date,
                            "symbol": r["symbol"], "ltp": r["ltp"], "ema9": r["ema9"],
                            "ema21": r["ema21"], "gap_pct": r["gap_pct"],
                            "ema9_slope": r["ema9_slope"], "ema21_slope": r["ema21_slope"],
                            "proximity_pct": r["proximity_pct"], "day_change_pct": r["day_change_pct"],
                            "sector": r["sector"], "touch_day": r["touch_day"]
                        })
                    conn.commit()
            except Exception as e:
                print(f"  DB save error: {e}")
        
        scan_progress["running"] = False
        scan_progress["phase"] = f"Chunk complete: {start_idx+1}-{end_idx} ({len(chunk_results)} matches)"
        
        return jsonify({
            "status": "complete",
            "start_idx": start_idx,
            "end_idx": end_idx,
            "next_idx": end_idx,
            "total": len(symbols),
            "results_count": len(chunk_results),
            "message": f"Scanned stocks {start_idx+1}-{end_idx}"
        })
        
    except Exception as e:
        scan_progress["running"] = False
        return jsonify({"error": str(e)}), 500


@app.route("/results")
def get_results():
    all_results = []
    
    # First, load any active chunk files (scan in progress)
    try:
        for chunk_file in sorted(os.listdir(CHUNK_DIR)):
            if chunk_file.endswith('.json'):
                chunk_path = os.path.join(CHUNK_DIR, chunk_file)
                with open(chunk_path, 'r') as f:
                    chunk_data = json.load(f)
                    all_results.extend(chunk_data)
    except Exception as e:
        print(f"  ⚠ Error loading chunks: {e}")
    
    # Then load from database (completed scans)
    if DB_TYPE == 'postgresql':
        try:
            with db_engine.connect() as conn:
                result = conn.execute(text("""SELECT symbol, ltp, ema9, ema21, gap_pct, ema9_slope, ema21_slope,
                            proximity_pct, day_change_pct, scan_date,
                            COALESCE(sector,''), COALESCE(touch_day,'')
                     FROM scan_results ORDER BY scan_date DESC, gap_pct ASC LIMIT 500"""))
                db_rows = result.fetchall()
                all_results.extend([{
                    "symbol": r[0], "ltp": r[1], "ema9": r[2], "ema21": r[3],
                    "gap_pct": r[4], "ema9_slope": r[5], "ema21_slope": r[6],
                    "proximity_pct": r[7], "day_change_pct": r[8], "scan_date": r[9],
                    "sector": r[10], "touch_day": r[11]
                } for r in db_rows])
        except Exception as e:
            print(f"  ⚠ DB error: {e}")
    else:
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        c.execute("""SELECT symbol, ltp, ema9, ema21, gap_pct, ema9_slope, ema21_slope,
                        proximity_pct, day_change_pct, scan_date,
                        COALESCE(sector,''), COALESCE(touch_day,'')
                 FROM scan_results ORDER BY scan_date DESC, gap_pct ASC LIMIT 500""")
        db_rows = c.fetchall()
        conn.close()
        all_results.extend([{
            "symbol": r[0], "ltp": r[1], "ema9": r[2], "ema21": r[3],
            "gap_pct": r[4], "ema9_slope": r[5], "ema21_slope": r[6],
            "proximity_pct": r[7], "day_change_pct": r[8], "scan_date": r[9],
            "sector": r[10], "touch_day": r[11]
        } for r in db_rows])
    
    # Remove duplicates (keep latest)
    seen = {}
    for r in all_results:
        key = (r.get('symbol'), r.get('scan_date', ''))
        seen[key] = r
    
    return jsonify(list(seen.values())[:500])


@app.route("/export")
def export_excel():
    if DB_TYPE == 'postgresql':
        with db_engine.connect() as conn:
            result = conn.execute(text("""SELECT symbol, ltp, ema9, ema21, gap_pct, ema9_slope, ema21_slope,
                        proximity_pct, day_change_pct, scan_date,
                        COALESCE(sector,''), COALESCE(touch_day,'')
                 FROM scan_results
                 WHERE scan_date = (SELECT MAX(scan_date) FROM scan_results)
                 ORDER BY sector ASC, gap_pct ASC"""))
            rows = result.fetchall()
    else:
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        c.execute("""SELECT symbol, ltp, ema9, ema21, gap_pct, ema9_slope, ema21_slope,
                        proximity_pct, day_change_pct, scan_date,
                        COALESCE(sector,''), COALESCE(touch_day,'')
                 FROM scan_results
                 WHERE scan_date = (SELECT MAX(scan_date) FROM scan_results)
                 ORDER BY sector ASC, gap_pct ASC""")
        rows = c.fetchall()
        conn.close()
    
    df = pd.DataFrame(rows, columns=["Symbol","LTP","EMA9","EMA21","Gap%",
                                      "EMA9 Slope%","EMA21 Slope%","Proximity%",
                                      "Day Chg%","Date","Sector","Touch Day"])
    buf = io.BytesIO()
    df.to_excel(buf, index=False, engine="openpyxl")
    buf.seek(0)
    fname = f"EMA9_Pullback_{date.today().strftime('%Y%m%d')}.xlsx"
    return send_file(buf, download_name=fname, as_attachment=True,
                     mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")


@app.route("/open/<symbol>")
def open_in_tradingview(symbol):
    """Open a symbol chart.

    macOS: TradingView desktop app on macOS does not support URL deep links
    and lacks a reliable way to open charts programmatically.
    Opens the chart in the default browser on tradingview.com.
    """
    sym = re.sub(r"[^A-Za-z0-9_&\-]", "", symbol).upper()
    tv_symbol = f"NSE:{sym}"
    url = f"https://www.tradingview.com/chart/?symbol={tv_symbol}"
    opened = False
    msg = ""

    try:
        import webbrowser
        webbrowser.open(url)
        opened = True
        msg = f"Opened {tv_symbol} chart in browser"
    except Exception as e:
        msg = str(e)

    return jsonify({"ok": opened, "url": url, "msg": msg})


@app.route("/")
def dashboard():
    """Main dashboard - original UI with chunk-based scanning for Render."""
    return render_template_string(HTML_TEMPLATE)


@app.route("/chunk")
def chunk_mode():
    """Chunk-by-chunk scanning mode for Render."""
    with open(os.path.join(os.path.dirname(__file__), 'chunk_scan.html'), 'r') as f:
        return f.read()


HTML_TEMPLATE = r"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>EMA9 Pullback Scanner</title>
<style>
  @import url('https://fonts.googleapis.com/css2?family=JetBrains+Mono:wght@300;400;500;600;700&display=swap');
  * { margin:0; padding:0; box-sizing:border-box; }
  body { background:#0a0a0a; color:#e5e5e5; font-family:'JetBrains Mono',monospace; font-size:13px; }
  .header { background:linear-gradient(135deg,#0f172a 0%,#1e1b4b 100%);
             padding:20px 28px; border-bottom:1px solid #1e293b; }
  .header h1 { font-size:20px; font-weight:700; color:#22d3ee; letter-spacing:1px; }
  .header .sub { color:#64748b; font-size:11px; margin-top:4px; }
  .toolbar { display:flex; gap:12px; align-items:center; padding:14px 28px;
             background:#111; border-bottom:1px solid #1e293b; flex-wrap:wrap; }
  .btn { padding:8px 18px; border:none; border-radius:4px; font-family:inherit;
         font-size:12px; font-weight:600; cursor:pointer; transition:all .15s; }
  .btn-scan { background:#22d3ee; color:#0a0a0a; }
  .btn-scan:hover { background:#06b6d4; }
  .btn-scan:disabled { background:#334155; color:#64748b; cursor:not-allowed; }
  .btn-export { background:#1e293b; color:#94a3b8; }
  .btn-export:hover { background:#334155; color:#e2e8f0; }
  .progress-bar { flex:1; min-width:200px; }
  .progress-outer { background:#1e293b; border-radius:3px; height:20px; overflow:hidden; position:relative; }
  .progress-inner { background:linear-gradient(90deg,#0891b2,#22d3ee); height:100%;
                     transition:width .3s; border-radius:3px; }
  .progress-text { position:absolute; top:0; left:0; right:0; height:100%; display:flex;
                    align-items:center; justify-content:center; font-size:10px; color:#e2e8f0;
                    font-weight:500; text-shadow:0 1px 2px rgba(0,0,0,.5); }
  .filter-info { padding:8px 28px; background:#0d1117; border-bottom:1px solid #1a1a1a;
                 font-size:10px; color:#475569; }
  .filter-info span { color:#94a3b8; }
  .controls { display:flex; gap:14px; align-items:center; padding:10px 28px;
              background:#0f0f0f; border-bottom:1px solid #1a1a1a; flex-wrap:wrap; }
  .controls label { color:#64748b; font-size:11px; text-transform:uppercase; letter-spacing:.5px; }
  .controls select, .controls input { background:#1e293b; color:#e5e5e5; border:1px solid #334155;
              padding:6px 10px; border-radius:4px; font-family:inherit; font-size:12px; min-width:180px; }
  .controls select:focus, .controls input:focus { outline:none; border-color:#22d3ee; }
  .controls .count-tag { color:#22d3ee; font-weight:600; }
  .controls .clear-btn { background:#3b0764; color:#c084fc; border:none; padding:6px 12px;
              border-radius:4px; cursor:pointer; font-family:inherit; font-size:11px; font-weight:600; }
  .controls .clear-btn:hover { background:#581c87; }
  .table-wrap { padding:12px 28px 40px; overflow-x:auto; }
  table { width:100%; border-collapse:collapse; }
  th { text-align:left; padding:10px 12px; color:#64748b; font-weight:500; font-size:11px;
       text-transform:uppercase; letter-spacing:.5px; border-bottom:1px solid #1e293b;
       cursor:pointer; user-select:none; white-space:nowrap; }
  th:hover { color:#94a3b8; }
  th.sorted-asc::after { content:" \u25B2"; color:#22d3ee; }
  th.sorted-desc::after { content:" \u25BC"; color:#22d3ee; }
  td { padding:9px 12px; border-bottom:1px solid #141414; white-space:nowrap; }
  tr:hover td { background:#111827; }
  .sym a { color:#f1f5f9; font-weight:600; text-decoration:none; }
  .sym a:hover { color:#22d3ee; text-decoration:underline; }
  .sector-cell { color:#94a3b8; font-size:11px; max-width:200px; overflow:hidden; text-overflow:ellipsis;
                  cursor:pointer; }
  .sector-cell:hover { color:#22d3ee; text-decoration:underline; }
  .num { text-align:right; font-variant-numeric:tabular-nums; }
  .pos { color:#4ade80; } .neg { color:#f87171; }
  .tag { display:inline-block; padding:2px 7px; border-radius:3px; font-size:10px; font-weight:600; }
  .tag-near { background:#164e63; color:#22d3ee; }
  .tag-below { background:#3b0764; color:#c084fc; }
  .tag-above { background:#14532d; color:#4ade80; }
  .touch-tag { display:inline-block; padding:2px 7px; border-radius:3px; font-size:10px;
               font-weight:600; background:#1e1b4b; color:#a78bfa; }
  .empty { text-align:center; padding:60px; color:#475569; }
  .empty h3 { font-size:16px; margin-bottom:8px; color:#64748b; }
  .toast-popup { position:fixed; bottom:30px; left:50%; transform:translateX(-50%); background:#1e293b;
                  color:#e2e8f0; padding:12px 24px; border-radius:6px; font-size:12px; font-weight:500;
                  box-shadow:0 4px 20px rgba(0,0,0,.5); border:1px solid #334155; z-index:9999;
                  opacity:0; transition:opacity .3s; pointer-events:none; }
  .toast-popup.show { opacity:1; }
  .toast-popup a { color:#22d3ee; text-decoration:none; font-weight:600; }
  .footer { padding:12px 28px; color:#334155; font-size:10px; text-align:center;
            border-top:1px solid #1a1a1a; }
</style>
</head>
<body>
<div class="header">
  <h1>&#9889; EMA9 PULLBACK SCANNER</h1>
  <div class="sub">NSE Stocks &middot; Upstox API (Free) &middot; Green candle LOW touching EMA9 &middot; LTP +0.5% to +4% &middot; LTP &lt; EMA9+6% &middot; Port 5037</div>
</div>
<div class="toolbar">
  <button class="btn btn-scan" id="btnScan" onclick="startScan()">&#9654; SCAN NOW</button>
  <button class="btn btn-export" onclick="location.href='/export'">&#11015; EXCEL</button>
  <div class="progress-bar">
    <div class="progress-outer">
      <div class="progress-inner" id="progBar" style="width:0%"></div>
      <div class="progress-text" id="progText">Ready</div>
    </div>
  </div>
</div>
<div class="filter-info">
  Filters: <span>Gap 4-10%</span> &middot; <span>EMA9 Slope -1.5 to 20%</span> &middot;
  <span>EMA21 Slope 2-15%</span> &middot; <span>LOW &plusmn;2% of EMA9 (last 5d)</span> &middot;
  <span>Green candle</span> &middot; <span>LTP +0.5% to +4% vs prev close</span> &middot;
  <span>LTP &lt; EMA9+6%</span>
</div>
<div class="controls">
  <label>Sector:</label>
  <select id="sectorFilter" onchange="renderTable()">
    <option value="">All sectors</option>
  </select>
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
    <thead>
      <tr>
        <th data-col="0">#</th><th data-col="1">Symbol</th><th data-col="2">Sector</th>
        <th data-col="3" class="num">LTP</th><th data-col="4" class="num">EMA9</th>
        <th data-col="5" class="num">EMA21</th><th data-col="6" class="num">Gap%</th>
        <th data-col="7" class="num">EMA9 Slope</th><th data-col="8" class="num">EMA21 Slope</th>
        <th data-col="9" class="num">Proximity</th><th data-col="10" class="num">Day Chg%</th>
        <th data-col="11">Touch</th>
      </tr>
    </thead>
    <tbody id="tbody"></tbody>
  </table>
  <div class="empty" id="emptyMsg">
    <h3>No results yet</h3>
    <p>Click SCAN NOW to find stocks pulling back to the 9 EMA</p>
  </div>
</div>
<div class="footer">EMA9 Pullback Scanner &middot; LOW &plusmn;2% touch &middot; LTP +0.5% to +4% &middot; LTP &lt; EMA9+6% &middot; Sector filter &middot; Port 5037</div>
<script>
let tableData=[], sortCol=6, sortDir='asc';
let scanRunning=false, scanIdx=0, scanTotal=0, scanChunks=0;

function toast(text){
  const t=document.getElementById('progText');
  if(t) t.textContent=text;
}
let _toastTimer;
function showToast(html, duration){
  let el=document.getElementById('toastPopup');
  if(!el){el=document.createElement('div');el.id='toastPopup';el.className='toast-popup';document.body.appendChild(el);}
  el.innerHTML=html;
  el.classList.add('show');
  clearTimeout(_toastTimer);
  _toastTimer=setTimeout(()=>el.classList.remove('show'), duration||4000);
}
function openTV(e, sym){
  e.preventDefault();
  fetch('/open/'+encodeURIComponent(sym))
    .then(r=>r.json())
    .then(d=>{ showToast(d.ok ? '\u2705 Opened <b>NSE:'+sym+'</b> in browser' : '\u274c Failed: '+d.msg, 3000); })
    .catch(()=>{ showToast('\u274c Failed to open chart', 3000); });
}

function startScan(){
  if(scanRunning) return;
  scanRunning=true; scanIdx=0; scanTotal=0; scanChunks=0;
  const b=document.getElementById('btnScan');
  b.disabled=true; b.textContent='SCANNING...';
  document.getElementById('progText').textContent='Starting scan...';
  scanNextChunk();
}

async function scanNextChunk(){
  if(!scanRunning) return;
  try{
    const resp=await fetch('/scan-chunk',{
      method:'POST',
      headers:{'Content-Type':'application/json'},
      body:JSON.stringify({start_idx:scanIdx})
    });
    const data=await resp.json();
    if(data.error){
      document.getElementById('progText').textContent='Error: '+data.error;
      stopScan(); return;
    }
    scanIdx=data.next_idx; scanTotal=data.total; scanChunks++;
    const pct=Math.round(scanIdx/scanTotal*100);
    document.getElementById('progBar').style.width=pct+'%';
    document.getElementById('progText').textContent=scanIdx+'/'+scanTotal+' ('+data.results_count+' matches)';
    loadResults();
    if(scanIdx>=scanTotal){
      document.getElementById('progText').textContent='Done! '+scanTotal+' stocks in '+scanChunks+' chunks ('+data.results_count+' total matches)';
      stopScan();
    } else {
      setTimeout(scanNextChunk, 1000);
    }
  } catch(e){
    document.getElementById('progText').textContent='Error: '+e.message;
    setTimeout(scanNextChunk, 3000);
  }
}

function stopScan(){
  scanRunning=false;
  const b=document.getElementById('btnScan');
  b.disabled=false; b.textContent='\u25B6 SCAN NOW';
}

function loadResults(){
  fetch('/results').then(r=>r.json()).then(data=>{
    tableData=data;
    if(!scanRunning){
      document.getElementById('btnScan').disabled=false;
      document.getElementById('btnScan').textContent='\u25B6 SCAN NOW';
    }
    document.getElementById('totalCount').textContent=data.length;
    if(data.length) document.getElementById('lastScan').textContent=data[0].scan_date;
    populateSectorDropdown();
    renderTable();
  });
}

function populateSectorDropdown(){
  const sel=document.getElementById('sectorFilter');
  const current=sel.value;
  const sectors={};
  tableData.forEach(r=>{const s=r.sector||'(no sector)'; sectors[s]=(sectors[s]||0)+1;});
  const sorted=Object.keys(sectors).sort();
  sel.innerHTML='<option value="">All sectors ('+tableData.length+')</option>';
  sorted.forEach(s=>{
    const opt=document.createElement('option');
    opt.value=s; opt.textContent=s+' ('+sectors[s]+')';
    sel.appendChild(opt);
  });
  sel.value=current;
}

function clearFilters(){
  document.getElementById('sectorFilter').value='';
  document.getElementById('symSearch').value='';
  renderTable();
}

function filterBySector(sector){
  document.getElementById('sectorFilter').value=sector||'(no sector)';
  renderTable();
}

function renderTable(){
  const tb=document.getElementById('tbody'),em=document.getElementById('emptyMsg');
  const sectorFilter=document.getElementById('sectorFilter').value;
  const symSearch=document.getElementById('symSearch').value.trim().toLowerCase();
  let filtered=tableData;
  if(sectorFilter){
    filtered=filtered.filter(r=>{
      const s=r.sector||'(no sector)';
      return s===sectorFilter;
    });
  }
  if(symSearch){
    filtered=filtered.filter(r=>r.symbol.toLowerCase().includes(symSearch));
  }
  document.getElementById('visibleCount').textContent=filtered.length;
  if(!filtered.length){tb.innerHTML=''; em.style.display='block'; em.querySelector('h3').textContent=tableData.length?'No matches':'No results yet'; return;}
  em.style.display='none';

  const keys=['','symbol','sector','ltp','ema9','ema21','gap_pct','ema9_slope','ema21_slope','proximity_pct','day_change_pct','touch_day'];
  const k=keys[sortCol];
  if(k){
    filtered.sort((a,b)=>{
      let va=a[k]||'',vb=b[k]||'';
      if(typeof va==='string'){va=va.toLowerCase();vb=vb.toLowerCase();}
      if(va<vb)return sortDir==='asc'?-1:1;
      if(va>vb)return sortDir==='asc'?1:-1;
      return 0;
    });
  }
  document.querySelectorAll('th').forEach(th=>{
    th.classList.remove('sorted-asc','sorted-desc');
    if(parseInt(th.dataset.col)===sortCol) th.classList.add('sorted-'+sortDir);
  });

  let h='';
  filtered.forEach((r,i)=>{
    const cc=r.day_change_pct>=0?'pos':'neg';
    const pc=Math.abs(r.proximity_pct)<0.5?'tag-near':r.proximity_pct<0?'tag-below':'tag-above';
    const pl=Math.abs(r.proximity_pct)<0.5?'NEAR':r.proximity_pct<0?'BELOW':'ABOVE';
    const u='https://www.tradingview.com/chart/?symbol=NSE%3A'+r.symbol;
    const sec=(r.sector||'').replace(/'/g,"\\'");
    h+='<tr>'+
      '<td style="color:#475569">'+(i+1)+'</td>'+
      '<td class="sym"><a href="javascript:void(0)" onclick="openTV(event,\''+r.symbol+'\')" title="Open in TradingView app">'+r.symbol+'</a></td>'+
      '<td class="sector-cell" onclick="filterBySector(\''+sec+'\')" title="Click to filter">'+(r.sector||'')+'</td>'+
      '<td class="num">\u20B9'+r.ltp.toLocaleString('en-IN',{minimumFractionDigits:2})+'</td>'+
      '<td class="num" style="color:#22d3ee">'+r.ema9.toFixed(2)+'</td>'+
      '<td class="num" style="color:#a78bfa">'+r.ema21.toFixed(2)+'</td>'+
      '<td class="num">'+r.gap_pct.toFixed(2)+'%</td>'+
      '<td class="num">'+r.ema9_slope.toFixed(2)+'%</td>'+
      '<td class="num">'+r.ema21_slope.toFixed(2)+'%</td>'+
      '<td class="num"><span class="tag '+pc+'">'+pl+' '+r.proximity_pct.toFixed(2)+'%</span></td>'+
      '<td class="num '+cc+'">+'+r.day_change_pct.toFixed(2)+'%</td>'+
      '<td><span class="touch-tag">'+(r.touch_day||'')+'</span></td>'+
    '</tr>';
  });
  tb.innerHTML=h;
}

document.querySelectorAll('th').forEach(th=>{
  th.addEventListener('click',()=>{
    const c=parseInt(th.dataset.col);
    if(c===sortCol) sortDir=sortDir==='asc'?'desc':'asc';
    else {sortCol=c; sortDir='asc';}
    renderTable();
  });
});
loadResults();
</script>
</body>
</html>
"""


if __name__ == "__main__":
    import webbrowser
    print(f"\n  EMA9 Pullback Scanner | Port {PORT} | Upstox API (Free)")
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
