# Railway.app Deployment Guide

## 🎯 Why Railway?

✅ **Free Tier**: $5 credit/month (enough for small apps)  
✅ **PostgreSQL**: Built-in, persistent database  
✅ **No Time Limits**: Scans can run 5-10 minutes  
✅ **Easy Setup**: Deploy from GitHub or CLI  
✅ **Auto SSL**: Free HTTPS  

---

## 📋 Pre-Deployment Checklist

### Files Created:
- ✅ `Procfile` - Railway start command
- ✅ `runtime.txt` - Python version
- ✅ `railway.json` - Railway configuration
- ✅ `requirements.txt` - Dependencies (updated)
- ✅ `.gitignore` - Exclude sensitive files
- ✅ `config.py` - Database auto-detection
- ✅ `app.py` - PostgreSQL support added

---

## 🚀 Step-by-Step Deployment

### Step 1: Install Railway CLI

```bash
# macOS
brew install railway

# Or via npm
npm i -g @railway/cli
```

### Step 2: Initialize Git Repository

```bash
cd /Users/vinodkumar/Desktop/StockMarketApp

# Initialize git
git init

# Add files
git add .

# Commit
git commit -m "Initial commit for Railway deployment"
```

### Step 3: Login to Railway

```bash
railway login
```

This will open your browser for authentication.

### Step 4: Create New Project

```bash
# Create project
railway init

# Name it: ema9-scanner (or your choice)
```

### Step 5: Add PostgreSQL Database

```bash
# Add PostgreSQL service
railway add postgresql
```

Or via Railway Dashboard:
1. Go to your project
2. Click "+ New"
3. Select "Database" → "Add PostgreSQL"
4. Railway auto-generates `DATABASE_URL`

### Step 6: Set Environment Variables

```bash
# Set Upstox token
railway variables set UPSTOX_ANALYTICS_TOKEN="your_token_here"

# Verify variables
railway variables
```

Or via Dashboard:
1. Go to your project
2. Click "Variables" tab
3. Add:
   - `UPSTOX_ANALYTICS_TOKEN`: Your Upstox analytics token

### Step 7: Deploy

```bash
# Connect to Railway project
railway link

# Deploy
railway up
```

This will:
- Upload your code
- Install dependencies
- Build the app
- Start with PostgreSQL

### Step 8: Get Your URL

```bash
# Get deployment URL
railway domain
```

Your app will be available at:
`https://your-app.up.railway.app`

---

## 🔄 Deployment via GitHub (Alternative)

### Option A: Deploy from GitHub Repo

1. **Push to GitHub**:
```bash
git remote add origin https://github.com/yourusername/ema9-scanner.git
git push -u origin main
```

2. **Deploy on Railway**:
   - Go to https://railway.app
   - Click "New Project"
   - Select "Deploy from GitHub repo"
   - Choose your repository
   - Railway auto-detects Python

3. **Add PostgreSQL**:
   - Click "+ New" → "Database" → "PostgreSQL"
   - `DATABASE_URL` is auto-set

4. **Set Variables**:
   - Go to "Variables" tab
   - Add `UPSTOX_ANALYTICS_TOKEN`

5. **Deploy**: Railway auto-deploys on every push!

---

## 📊 Database Migration

### Current SQLite → PostgreSQL

Your app now **automatically** uses:
- **PostgreSQL** on Railway (via `DATABASE_URL`)
- **SQLite** locally (for development)

### Tables Created:
```sql
- scan_results (scanner hits)
- scan_log (scan history)
- sector_cache (sector data cache)
```

### Storage on Railway:
- **Current DB size**: ~32 KB
- **Railway free tier**: 5 GB PostgreSQL
- **You can store**: ~150,000x more data! ✅

---

## ⚙️ Configuration Explained

### `config.py` Auto-Detection:
```python
if DATABASE_URL:
    # Railway → PostgreSQL
    DB_TYPE = 'postgresql'
else:
    # Local → SQLite
    DB_TYPE = 'sqlite'
```

### `Procfile`:
```
web: gunicorn app:app --timeout 600 --workers 1
```
- **timeout 600**: Allows 10-minute scans
- **gunicorn**: Production WSGI server

### `railway.json`:
```json
{
  "deploy": {
    "startCommand": "gunicorn app:app --timeout 600 --workers 1",
    "healthcheckPath": "/",
    "restartPolicyType": "ON_FAILURE"
  }
}
```

---

## 💰 Cost Breakdown

### Railway Free Tier:
- **$5 credit/month** (renews monthly)
- **5 GB PostgreSQL** storage
- **512 MB RAM** per service
- **Shared CPU**

### Your App Usage:
- **RAM**: ~200 MB (well within 512 MB)
- **Storage**: ~32 KB (well within 5 GB)
- **CPU**: Low (only during scans)
- **Estimated Cost**: ~$2-3/month (within free tier!)

### If You Need More:
- **Hobby Plan**: $5/month (always $5 credit)
- **Pro Plan**: $20/month (more resources)

---

## 🔧 Troubleshooting

### Issue: App won't start
```bash
# Check logs
railway logs

# Common fixes:
# 1. Verify DATABASE_URL is set
railway variables

# 2. Check build logs
railway logs --deployment
```

### Issue: Scanner times out
- Already configured for 600 seconds (10 min)
- Check Railway dashboard for resource usage

### Issue: Database connection error
```bash
# Verify PostgreSQL is running
railway status

# Check DATABASE_URL format
railway variables | grep DATABASE_URL
```

### Issue: Upstox token not working
```bash
# Re-set the token
railway variables set UPSTOX_ANALYTICS_TOKEN="new_token"

# Redeploy
railway up
```

---

## 📈 Monitoring

### View Logs:
```bash
railway logs
```

### Check Database:
```bash
# Open psql console
railway psql

# Run queries
SELECT COUNT(*) FROM scan_results;
SELECT * FROM scan_log ORDER BY created_at DESC LIMIT 5;
```

### Dashboard:
- Go to https://railway.app
- Select your project
- View metrics, logs, database

---

## 🔄 Updating Your App

### After making changes:
```bash
# Commit changes
git add .
git commit -m "Update scanner filters"

# Deploy
railway up

# Or if using GitHub:
git push origin main  # Auto-deploys!
```

---

## 🎉 Post-Deployment

Your app will be available at:
```
https://your-project.up.railway.app
```

### Features:
✅ Full scanner functionality  
✅ Persistent PostgreSQL database  
✅ HTTPS enabled  
✅ Auto-restarts on failure  
✅ Sector caching works  
✅ Export to Excel works  
✅ Scan history preserved  

### Access from anywhere:
- Phone, tablet, any computer
- No need to keep your Mac running
- Share with team members

---

## 🆘 Need Help?

### Railway Docs:
- https://docs.railway.app

### Railway CLI Commands:
```bash
railway --help           # All commands
railway status           # Project status
railway logs             # View logs
railway variables        # Environment vars
railway domain           # Custom domain
railway unlink           # Disconnect project
```

---

## 🎯 Quick Start Commands

```bash
# 1. Install CLI
brew install railway

# 2. Login
railway login

# 3. Create project
cd /Users/vinodkumar/Desktop/StockMarketApp
railway init
railway add postgresql

# 4. Set variables
railway variables set UPSTOX_ANALYTICS_TOKEN="your_token"

# 5. Deploy
railway up

# 6. Get URL
railway domain
```

**Done! Your scanner is now live on the cloud! 🚀**
