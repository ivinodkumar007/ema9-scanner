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
        Downloads from Upstox JSON instrument file (BOD)."""
        if self._instrument_cache and self._instrument_cache.get("exchange") == exchange:
            return self._instrument_cache["data"]
        
        # Upstox JSON instrument URLs (CSV is deprecated)
        urls = [
            f"https://assets.upstox.com/market-quote/instruments/exchange/{exchange.lower()}.json.gz",
            f"https://assets.upstox.com/market-quote/instruments/exchange/complete.json.gz",
        ]
        
        for url in urls:
            try:
                import gzip
                import json as json_lib
                
                print(f"  Downloading instruments from: {url[:80]}...")
                r = requests.get(url, timeout=30)
                print(f"  Response: {r.status_code}, size: {len(r.content)} bytes")
                
                if r.status_code == 200 and len(r.content) > 100:
                    # Decompress gzip
                    if url.endswith('.gz'):
                        data = json_lib.loads(gzip.decompress(r.content))
                    else:
                        data = r.json()
                    
                    instruments = []
                    # JSON can be a dict or list
                    items = []
                    if isinstance(data, dict):
                        items = list(data.values())
                    elif isinstance(data, list):
                        items = data
                    
                    print(f"    JSON has {len(items)} items")
                    if items and isinstance(items[0], dict):
                        print(f"    Sample keys: {list(items[0].keys())[:10]}")
                    
                    for inst in items:
                        if not isinstance(inst, dict):
                            continue
                        segment = inst.get("segment", "")
                        inst_type = inst.get("instrument_type", "")
                        exchange_val = inst.get("exchange", "")
                        # Accept NSE equity instruments
                        if segment == "NSE_EQ" and inst_type in ("EQ", "BE", "BZ", ""):
                            instruments.append({
                                "tradingsymbol": inst.get("trading_symbol", ""),
                                "instrument_key": inst.get("instrument_key", ""),
                                "instrument_token": inst.get("exchange_token", ""),
                                "exchange": exchange_val,
                                "isin": inst.get("isin", "")
                            })
                    
                    print(f"    Filtered to {len(instruments)} NSE_EQ instruments")
                    if instruments:
                        samples = [i["tradingsymbol"] for i in instruments[:5]]
                        print(f"    Sample symbols: {samples}")
                    
                    if instruments:
                        self._instrument_cache = {"exchange": exchange, "data": instruments}
                        print(f"  ✓ Loaded {len(instruments)} {exchange} instruments")
                        return instruments
            except Exception as e:
                print(f"  ⚠ Instrument download error from {url[:60]}: {e}")
        
        print(f"  ⚠ Failed to load instruments from all URLs")
        return []
    
    def _get_instrument_token(self, symbol, isin=""):
        """Get instrument key for a symbol (used in API calls).
        
        Args:
            symbol: Trading symbol (e.g., "RELIANCE")
            isin: ISIN number (e.g., "INE002A01018") - more reliable match
        
        Returns:
            instrument_key like "NSE_EQ|INE002A01018" or None
        """
        if self._instrument_cache is None:
            self.instruments("NSE")
        
        # If still None (download failed), initialize empty cache
        if self._instrument_cache is None:
            self._instrument_cache = {"exchange": "NSE", "data": []}
            return None
        
        # Try ISIN match first (most reliable)
        if isin:
            for inst in self._instrument_cache["data"]:
                if inst.get("isin", "").upper() == isin.upper():
                    return inst.get("instrument_key") or inst.get("instrument_token")
        
        # Fallback to symbol match
        for inst in self._instrument_cache["data"]:
            if inst.get("tradingsymbol", "").upper() == symbol.upper():
                return inst.get("instrument_key") or inst.get("instrument_token")
        return None
    
    def historical_data(self, symbol, from_date, to_date, interval="day", isin=""):
        """Get historical candle data (V3 API).
        
        Args:
            symbol: Symbol name (e.g., "RELIANCE")
            from_date: Start date (datetime.date)
            to_date: End date (datetime.date)
            interval: "day", "minute", "3minute", "5minute", etc.
            isin: ISIN number for exact instrument match
        
        Returns:
            List of candle dicts with: date, open, high, low, close, volume
        """
        token = self._get_instrument_token(symbol, isin=isin)
        if not token:
            # Log first few missing symbols for debugging
            if not hasattr(self, '_missing_count'):
                self._missing_count = 0
            if self._missing_count < 5:
                cache_size = len(self._instrument_cache["data"]) if self._instrument_cache else 0
                print(f"  ⚠ No token for '{symbol}' (cache has {cache_size} instruments)")
                # Try fuzzy match
                if self._instrument_cache and self._instrument_cache["data"]:
                    matches = [i["tradingsymbol"] for i in self._instrument_cache["data"] 
                              if symbol.upper() in i.get("tradingsymbol", "").upper()][:5]
                    if matches:
                        print(f"    Similar symbols: {matches}")
                    else:
                        print(f"    No similar matches found")
                    # Also check name field
                    name_matches = [i.get("tradingsymbol", "") for i in self._instrument_cache["data"]
                                   if symbol.replace(" ", "") in i.get("name", "").replace(" ", "").upper()][:5]
                    if name_matches:
                        print(f"    Name matches: {name_matches}")
            self._missing_count += 1
            return []
        
        # token is now instrument_key like "NSE_EQ|INE002A01018"
        instrument_key = token if "|" in str(token) else f"NSE_EQ|{token}"
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
    
    def ohlc(self, symbol, isin=""):
        """Get OHLC and LTP data for a symbol (V3 API).
        
        Returns:
            Dict with last_price and ohlc data
        """
        token = self._get_instrument_token(symbol, isin=isin)
        if not token:
            return None
        
        # token is now instrument_key like "NSE_EQ|INE002A01018"
        instrument_key = token if "|" in str(token) else f"NSE_EQ|{token}"
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
