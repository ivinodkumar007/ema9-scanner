# Vercel Deployment Guide

## 📊 Storage Analysis

### Current Data Usage:
- **SQLite Database**: 32 KB (ema9pullback.db)
  - scan_results: 32 records
  - scan_log: 3 records  
  - sector_cache: 32 records
- **NSE Equity List**: 115 KB (EQUITY_L.csv) - static file
- **Total Storage**: ~150 KB

### Vercel Free Tier Limits:
- ✅ **Serverless Function Storage**: 1 MB per deployment
- ✅ **Ephemeral /tmp Storage**: 512 MB per function invocation
- ✅ **Serverless Execution Time**: 10 seconds (free) / 300 seconds (pro)
- ⚠️ **Database**: SQLite in /tmp is **ephemeral** (lost between invocations)

### ⚠️ Important: Database Limitation on Vercel

**Problem**: Vercel serverless functions are stateless. SQLite in `/tmp` is deleted after each scan completes.

**Impact**:
- ✅ Scanning works fine
- ❌ Results are lost between scans (unless exported immediately)
- ❌ Sector cache is lost (will re-fetch every scan)

**Solutions** (Choose one):

#### Option 1: Keep Local (Recommended for Free Tier)
Run locally on your Mac - SQLite works perfectly, no data loss.

#### Option 2: Use Free Cloud Database
Migrate to PostgreSQL (Neon.tech offers free 512 MB):
```bash
# Install Vercel Postgres or use Neon
DATABASE_URL=postgresql://user:pass@host/db
```
Requires code changes to use SQLAlchemy instead of SQLite.

#### Option 3: Accept Ephemeral Storage
- Export results immediately after each scan (Excel download works)
- Sector data refetched each time (adds ~30 sec to scan)

---

## 🚀 Deployment Steps

### Prerequisites
1. Vercel CLI installed: `npm i -g vercel`
2. Vercel account created
3. Git repository initialized

### Step 1: Initialize Git
```bash
cd /Users/vinodkumar/Desktop/StockMarketApp
git init
git add .
git commit -m "Initial commit for Vercel deployment"
```

### Step 2: Deploy to Vercel
```bash
# Login to Vercel
vercel login

# Deploy
vercel
```

### Step 3: Set Environment Variables
```bash
vercel env add UPSTOX_ANALYTICS_TOKEN
# Paste your token when prompted
```

### Step 4: Configure Function Duration (Required for Scanner)
The scanner takes ~5-10 minutes. Vercel free tier only allows 10 seconds.

**Options**:
- Upgrade to Vercel Pro ($20/month) for 300 second functions
- OR: Keep running locally (free, no limitations)

---

## ⚡ Quick Deploy Command

```bash
cd /Users/vinodkumar/Desktop/StockMarketApp
vercel --prod
```

---

## 🎯 Recommendation

**For your use case, I recommend:**

### Keep Running Locally ✅
- **Cost**: Free
- **Storage**: Unlimited (your Mac's disk)
- **Execution Time**: No limits
- **Data Persistence**: SQLite works perfectly
- **Background Scanning**: Can run 24/7

**Why?**
1. Scanner needs 5-10 minutes (exceeds Vercel free tier's 10 sec limit)
2. SQLite needs persistent storage (Vercel /tmp is ephemeral)
3. Vercel Pro costs $20/month (vs free local)
4. You already have it working perfectly on your Mac

### Alternative: Use a VPS
If you need cloud deployment:
- **DigitalOcean**: $4-6/month (1 GB RAM, 25 GB SSD)
- **Railway.app**: Free tier with PostgreSQL
- **Render.com**: Free tier for web services

---

## 📝 Files Created for Vercel

1. **vercel.json** - Vercel configuration
2. **wsgi.py** - WSGI entry point
3. **requirements.txt** - Python dependencies

All set up and ready if you decide to deploy!

---

## 🔧 If You Still Want to Deploy

### Upgrade Requirements:
1. **Vercel Pro**: $20/month (300 sec functions)
2. **Neon PostgreSQL**: Free 512 MB (for persistent data)

### Migration Steps:
1. Create Neon database at https://neon.tech
2. Get DATABASE_URL
3. Install SQLAlchemy: `pip install sqlalchemy psycopg2`
4. Update app.py to use PostgreSQL instead of SQLite
5. Deploy with: `vercel --prod`

Let me know if you want help with the PostgreSQL migration!
