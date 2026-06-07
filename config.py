# ============================================
# EMA9 Pullback Scanner — config.py
# (Reconstructed: required by app.py and auth.py)
# ============================================
import os
import json

# ---- Paths ----------------------------------------------------------------
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DESKTOP = os.path.join(os.path.expanduser("~"), "Desktop")  # token cache lives under DESKTOP/SectorScanner/

# Database configuration
# Railway provides DATABASE_URL for PostgreSQL
# Fallback to SQLite for local development
DATABASE_URL = os.environ.get('DATABASE_URL', '')

if DATABASE_URL:
    # Railway deployment - use PostgreSQL
    DB_TYPE = 'postgresql'
    DB_PATH = DATABASE_URL
else:
    # Local development - use SQLite
    DB_TYPE = 'sqlite'
    DATA_DIR = BASE_DIR
    DB_PATH = os.path.join(DATA_DIR, "ema9pullback.db")

NSE_STOCKS_FILE = os.path.join(BASE_DIR, "EQUITY_L.csv")

# ---- Web server -----------------------------------------------------------
PORT = 5037

# ---- Historical data window ----------------------------------------------
CANDLE_DAYS = 120  # how many calendar days of daily candles to pull

# ---- Scan filter parameters (mirrors update_app.py) -----------------------
GAP_PCT_MIN = 4.00          # EMA9 vs EMA21 gap, min %
GAP_PCT_MAX = 10.00         # EMA9 vs EMA21 gap, max %

EMA9_SLOPE5_MIN = -1.50     # EMA9 5-day slope, min %
EMA9_SLOPE5_MAX = 20.00     # EMA9 5-day slope, max %

EMA21_SLOPE5_MIN = 2.00     # EMA21 5-day slope, min %
EMA21_SLOPE5_MAX = 15.00    # EMA21 5-day slope, max %

TOUCH_BELOW = 0.02          # LOW allowed this far BELOW EMA9 (fraction, 0.02 = 2%)
TOUCH_ABOVE = 0.02          # LOW allowed this far ABOVE EMA9 (fraction)
TOUCH_LOOKBACK = 5          # look back this many days for the touch

INTRADAY_GAIN_MIN = 0.50    # LTP vs prev close, min %
INTRADAY_GAIN_MAX = 4.00    # LTP vs prev close, max %

LTP_EMA9_MAX = 6.00         # LTP must be < EMA9 * (1 + this%/100)

# ---- Gmail alert (optional) ----------------------------------------------
# Leave blank to disable email. To enable, set a Gmail address + App Password
# (https://myaccount.google.com/apppasswords). Can also be set via env vars.
GMAIL_SENDER = os.environ.get("GMAIL_SENDER", "")
GMAIL_APP_PASSWORD = os.environ.get("GMAIL_APP_PASSWORD", "")
GMAIL_RECIPIENT = os.environ.get("GMAIL_RECIPIENT", "")


# ---- Upstox API credentials ----------------------------------------------
# read_keys() returns the credentials auth.py needs. It looks for a
# keys.json file next to this config first, then falls back to env vars.
#
# keys.json format:
# {
#   "UPSTOX_ANALYTICS_TOKEN": "your_analytics_token_here"
# }
_KEYS_FILE = os.path.join(BASE_DIR, "keys.json")

_KEY_NAMES = [
    "UPSTOX_ANALYTICS_TOKEN",
]


def read_keys():
    """Return a dict of Zerodha credentials from keys.json or environment."""
    keys = {}
    if os.path.exists(_KEYS_FILE):
        try:
            with open(_KEYS_FILE, "r", encoding="utf-8") as f:
                keys = json.load(f)
        except Exception as e:
            print(f"  WARNING: could not read keys.json: {e}")
    # Environment variables override / fill in
    for name in _KEY_NAMES:
        if os.environ.get(name):
            keys[name] = os.environ[name]
        keys.setdefault(name, "")
    return keys
