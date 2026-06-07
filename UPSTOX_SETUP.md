# Upstox Analytics Token Setup Guide

## 1. Get Your Analytics Token

1. Go to [Upstox Developer Portal](https://developer.upstox.com/)
2. Login to your account
3. Navigate to **Analytics** or **API Tokens** section
4. Copy your analytics token

## 2. Configure keys.json

Edit `/Users/vinodkumar/Desktop/StockMarketApp/keys.json`:

```json
{
  "UPSTOX_ANALYTICS_TOKEN": "paste_your_analytics_token_here"
}
```

## 3. Run the Scanner

```bash
cd ~/Desktop/StockMarketApp
source venv/bin/activate
python app.py
```

## Benefits of Analytics Token

- **No OAuth flow** - No browser login required
- **No expiry** - Token doesn't expire like OAuth tokens (24h)
- **FREE** - Access to all market data APIs
- **Simple setup** - Just paste the token in keys.json

## What You Get

- ✅ Historical candle data (daily, minute, etc.)
- ✅ Real-time OHLC quotes
- ✅ Instrument master file
- ✅ Market depth and quotes
- ✅ All data APIs (read-only)

## API Rate Limits

- Upstox allows **~1000 requests/minute** (more than enough for the scanner)
- Historical candle data: 200 candles per request
- Free tier includes all data APIs
