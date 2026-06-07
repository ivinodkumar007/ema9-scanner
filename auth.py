# ============================================
# EMA9 Pullback Scanner — Upstox Auth
# ============================================

import os, json, time, requests
from config import read_keys, DESKTOP, PORT

TOKEN_CACHE = os.path.join(DESKTOP, "SectorScanner", "upstox_token.json")
TOKEN_MAX_AGE = 23 * 3600  # 23 hours (Upstox tokens expire in 24h)

UPSTOX_API = "https://api.upstox.com"


def get_cached_token():
    """Return cached access token if still fresh."""
    if not os.path.exists(TOKEN_CACHE):
        return None
    try:
        with open(TOKEN_CACHE, "r") as f:
            data = json.load(f)
        if time.time() - data.get("timestamp", 0) < TOKEN_MAX_AGE:
            return data.get("access_token")
    except Exception:
        pass
    return None


def save_token(token):
    """Save access token to shared cache."""
    os.makedirs(os.path.dirname(TOKEN_CACHE), exist_ok=True)
    with open(TOKEN_CACHE, "w") as f:
        json.dump({"access_token": token, "timestamp": time.time()}, f)


class UpstoxClient:
    """Lightweight Upstox API client."""
    
    def __init__(self, access_token):
        self.access_token = access_token
        self.headers = {
            "Accept": "application/json",
            "Authorization": f"Bearer {access_token}",
            "Content-Type": "application/x-www-form-urlencoded"
        }
        self._instrument_cache = None
    
    def profile(self):
        """Get user profile to test authentication."""
        r = requests.get(
            f"{UPSTOX_API}/v2/user/profile",
            headers={
                'Content-Type': 'application/json',
                'Accept': 'application/json',
                'Authorization': f'Bearer {self.access_token}'
            },
            timeout=10
        )
        if r.status_code != 200:
            print(f"  Profile API response: {r.status_code} - {r.text[:200]}")
        r.raise_for_status()
        return r.json()
    
    def instruments(self, exchange="NSE"):
        """Get all instruments for an exchange.
        Downloads from Upstox public instrument file."""
        if self._instrument_cache and self._instrument_cache.get("exchange") == exchange:
            return self._instrument_cache["data"]
        
        # Try multiple Upstox instrument URLs
        urls = [
            f"https://assets.upstox.com/assets/upstox-assets/market_data/instruments/{exchange.lower()}_contracts.csv",
            f"https://assets.upstox.com/market-quote/instruments/exchange/{exchange.lower()}.csv",
        ]
        
        for url in urls:
            try:
                print(f"  Downloading instruments from: {url[:80]}...")
                r = requests.get(url, timeout=30)
                print(f"  Response: {r.status_code}, size: {len(r.text)} bytes")
                
                if r.status_code == 200 and len(r.text) > 100:
                    import csv
                    import io
                    
                    csv_file = io.StringIO(r.text)
                    reader = csv.DictReader(csv_file)
                    instruments = []
                    for row in reader:
                        instruments.append({
                            "tradingsymbol": row.get("tradingsymbol", ""),
                            "instrument_token": row.get("instrument_token", ""),
                            "exchange": row.get("exchange", "")
                        })
                    
                    if instruments:
                        self._instrument_cache = {"exchange": exchange, "data": instruments}
                        print(f"  ✓ Loaded {len(instruments)} {exchange} instruments")
                        return instruments
            except Exception as e:
                print(f"  ⚠ Instrument download error from {url[:60]}: {e}")
        
        print(f"  ⚠ Failed to load instruments from all URLs")
        return []
    
    def _get_instrument_token(self, symbol):
        """Get instrument token for a symbol."""
        if self._instrument_cache is None:
            self.instruments("NSE")
        
        # If still None (download failed), initialize empty cache
        if self._instrument_cache is None:
            self._instrument_cache = {"exchange": "NSE", "data": []}
            return None
        
        for inst in self._instrument_cache["data"]:
            if inst.get("tradingsymbol") == symbol:
                return inst.get("instrument_token")
        return None
    
    def historical_data(self, symbol, from_date, to_date, interval="day"):
        """Get historical candle data (V3 API).
        
        Args:
            symbol: Symbol name (e.g., "RELIANCE")
            from_date: Start date (datetime.date)
            to_date: End date (datetime.date)
            interval: "day", "minute", "3minute", "5minute", etc.
        
        Returns:
            List of candle dicts with: date, open, high, low, close, volume
        """
        token = self._get_instrument_token(symbol)
        if not token:
            # Log first few missing symbols for debugging
            if not hasattr(self, '_missing_count'):
                self._missing_count = 0
            if self._missing_count < 5:
                cache_size = len(self._instrument_cache["data"]) if self._instrument_cache else 0
                print(f"  ⚠ No token for '{symbol}' (cache has {cache_size} instruments)")
                # Show first few symbols in cache for comparison
                if self._instrument_cache and self._instrument_cache["data"]:
                    samples = [i.get("tradingsymbol") for i in self._instrument_cache["data"][:5]]
                    print(f"    Cache samples: {samples}")
            self._missing_count += 1
            return []
        
        # Upstox V3 Historical Candle API
        # Format: /v3/historical-candle/{instrument_key}/{interval}/{to_date}/{from_date}
        instrument_key = f"NSE_EQ|{token}"
        url = f"{UPSTOX_API}/v3/historical-candle/{instrument_key}/{interval}/{to_date.isoformat()}/{from_date.isoformat()}"
        
        try:
            r = requests.get(
                url,
                headers={
                    'Accept': 'application/json',
                    'Authorization': f'Bearer {self.access_token}'
                },
                timeout=15
            )
            data = r.json()
            
            if data.get("status") == "success":
                candles = data.get("data", {}).get("candles", [])
                # Convert to Zerodha-compatible format
                return [
                    {
                        "date": c[0],
                        "open": c[1],
                        "high": c[2],
                        "low": c[3],
                        "close": c[4],
                        "volume": c[5] if len(c) > 5 else 0
                    }
                    for c in candles
                ]
        except Exception as e:
            print(f"  ⚠ Historical data error for {symbol}: {e}")
        
        return []
    
    def ohlc(self, symbol):
        """Get OHLC and LTP data for a symbol (V3 API).
        
        Returns:
            Dict with last_price and ohlc data
        """
        token = self._get_instrument_token(symbol)
        if not token:
            return None
        
        # Upstox V3 OHLC Quote API
        # Format: /v3/market-quote/ohlc?symbol=NSE_EQ|{instrument_token}
        instrument_key = f"NSE_EQ|{token}"
        url = f"{UPSTOX_API}/v3/market-quote/ohlc?symbol={instrument_key}"
        
        try:
            r = requests.get(
                url,
                headers={
                    'Accept': 'application/json',
                    'Authorization': f'Bearer {self.access_token}'
                },
                timeout=10
            )
            data = r.json()
            
            if data.get("status") == "success":
                quote_data = data.get("data", {}).get(instrument_key, {})
                return {
                    "last_price": quote_data.get("last_price", 0),
                    "ohlc": {
                        "open": quote_data.get("ohlc", {}).get("open", 0),
                        "high": quote_data.get("ohlc", {}).get("high", 0),
                        "low": quote_data.get("ohlc", {}).get("low", 0),
                        "close": quote_data.get("ohlc", {}).get("close", 0)
                    }
                }
        except Exception as e:
            print(f"  ⚠ OHLC error for {symbol}: {e}")
        
        return None


def get_kite():
    """Return authenticated UpstoxClient instance (named 'kite' for compatibility)."""
    keys = read_keys()
    
    # Use analytics token from keys.json
    analytics_token = keys.get("UPSTOX_ANALYTICS_TOKEN", "")
    
    if analytics_token:
        print(f"  ✓ Using Upstox analytics token")
        # Analytics token is read-only for Market Data
        # We'll validate on first API call, just create the client
        client = UpstoxClient(analytics_token)
        print(f"  ✓ Client initialized (will validate on first scan)")
        return client
    
    # Fallback to cached token
    token = get_cached_token()
    if token:
        client = UpstoxClient(token)
        try:
            client.profile()
            return client
        except Exception:
            pass
    
    print("  ✗ No Upstox analytics token found in keys.json")
    print("  Please add UPSTOX_ANALYTICS_TOKEN to your keys.json file")
    return None
