# Render.com Deployment Guide - FREE FOREVER! 🎉

## 💰 Cost: $0/month - Forever!

Your EMA9 Pullback Scanner will run on Render's free tier with:
- ✅ **750 free hours/month** (renews monthly)
- ✅ **Free PostgreSQL database** 
- ✅ **Manual scans** (click button when needed)
- ✅ **No credit card required**

---

## 📋 What's Been Prepared

### Files Created:
1. ✅ `render.yaml` - Render configuration
2. ✅ `Procfile` - Production server setup
3. ✅ `requirements.txt` - All dependencies
4. ✅ `runtime.txt` - Python 3.13
5. ✅ `.gitignore` - Security
6. ✅ `app.py` - PostgreSQL support added
7. ✅ `config.py` - Auto-detects database type

### Database Support:
- ✅ **SQLite** (local development)
- ✅ **PostgreSQL** (Render deployment)
- Auto-switches based on environment!

---

## 🚀 Step-by-Step Deployment

### Step 1: Push to GitHub

```bash
cd /Users/vinodkumar/Desktop/StockMarketApp

# Add remote (replace with your GitHub repo URL)
git remote add origin https://github.com/YOUR_USERNAME/ema9-scanner.git

# Push code
git push -u origin main
```

**Don't have a repo yet?** Create one:
1. Go to https://github.com/new
2. Name: `ema9-scanner`
3. Click "Create repository"
4. Copy the URL and use in step above

---

### Step 2: Sign Up for Render

1. Go to https://render.com
2. Click **"Get Started for Free"**
3. Sign up with GitHub (easiest)
4. No credit card needed!

---

### Step 3: Deploy Web Service

1. **Go to Dashboard**: https://dashboard.render.com

2. **Click "New +"** → **"Web Service"**

3. **Connect Repository**:
   - Select your `ema9-scanner` repo
   - Or paste: `https://github.com/YOUR_USERNAME/ema9-scanner.git`

4. **Configure Service**:
   ```
   Name: ema9-scanner
   Region: Oregon (closest to India)
   Branch: main
   Root Directory: (leave blank)
   Runtime: Python 3
   ```

5. **Build & Start Commands**:
   ```
   Build Command: pip install -r requirements.txt
   Start Command: gunicorn app:app --timeout 600 --workers 1 --bind 0.0.0.0:$PORT
   ```

6. **Instance Type**: Select **"Free"**

7. **Click "Advanced"** and add environment variables:
   ```
   UPSTOX_ANALYTICS_TOKEN = your_actual_token_here
   PYTHON_VERSION = 3.13.0
   ```

8. **Click "Create Web Service"**

---

### Step 4: Add PostgreSQL Database

1. **Go to your project** in Render Dashboard

2. **Click "New +"** → **"PostgreSQL"**

3. **Configure Database**:
   ```
   Name: ema9-postgres
   Region: Oregon (same as web service)
   Instance Type: Free
   PostgreSQL Version: 15 (or latest)
   ```

4. **Click "Create Database"**

5. **Copy the Connection String**:
   - Render shows: `postgresql://user:pass@host/dbname`
   - Copy this! You'll need it.

---

### Step 5: Connect Database to Web Service

1. **Go to your Web Service** settings

2. **Click "Environment"** tab

3. **Add DATABASE_URL**:
   ```
   Key: DATABASE_URL
   Value: (paste the PostgreSQL connection string from Step 4)
   ```

4. **Click "Save Changes"**

5. **Service will auto-redeploy** - wait 2-3 minutes

---

### Step 6: Get Your Live URL

1. **Go to your Web Service** in dashboard

2. **Find the URL** at the top:
   ```
   https://ema9-scanner-xxxx.onrender.com
   ```

3. **Bookmark it!** This is your scanner dashboard

---

## ✅ Verify Everything Works

### Test 1: Open Dashboard
```
Visit: https://ema9-scanner-xxxx.onrender.com
You should see the EMA9 Pullback Scanner UI
```

### Test 2: Run a Scan
1. Click **"Scan Now"** button
2. Wait 5-10 minutes
3. Results should appear in the table

### Test 3: Export Results
1. Click **"Export Excel"**
2. File should download

---

## 🔄 Database Renewal (Every 30 Days)

Render's free PostgreSQL expires after 30 days. **Easy fix:**

### When Database Expires:
1. **Go to Render Dashboard**
2. **Delete old database**: Click database → Settings → Delete
3. **Create new database**: Follow Step 4 again
4. **Update DATABASE_URL**: Follow Step 5 again
5. **Web service auto-reconnects**

**Takes 5 minutes, costs $0!**

---

## 💡 How It Works

### Free Tier Mechanics:

**Web Service:**
- 750 hours/month = 24/7 for 1 service
- **Spins down after 15 min idle** (saves hours!)
- Wakes up in ~1 minute when accessed
- Hours reset every month

**Your Usage:**
- Active scans: ~30 min/day max
- Idle time: Spins down (no hours used!)
- **Actual hours used**: ~200-300/month
- **Free allowance**: 750 hours
- **You're well within limits!** ✅

---

## 📱 Access From Anywhere

Your scanner is now live at:
```
https://ema9-scanner-xxxx.onrender.com
```

**Access from:**
- ✅ Phone browser
- ✅ Tablet
- ✅ Any computer
- ✅ Share with team members

---

## ⚙️ Features Available

✅ **Manual Scans** - Click "Scan Now" anytime  
✅ **View Results** - Interactive table with sorting  
✅ **Export to Excel** - Download scan results  
✅ **Sector Lookup** - Automatic from Screener.in  
✅ **Scan History** - All results in PostgreSQL  
✅ **HTTPS** - Secure connection  
✅ **Mobile Friendly** - Works on all devices  

---

## 🔧 Troubleshooting

### Issue: "Service Not Found"
```
Solution: Wait 2-3 minutes after deploy
Render needs time to build and start
```

### Issue: Database Connection Error
```
Solution: 
1. Check DATABASE_URL is correct
2. PostgreSQL database is running
3. Redeploy web service
```

### Issue: Scan Fails
```
Solution:
1. Check UPSTOX_ANALYTICS_TOKEN is set
2. View logs in Render Dashboard
3. Token might be expired - regenerate
```

### Issue: App is Slow to Load
```
Solution: Normal! Free tier spins down after 15 min
First load takes ~1 minute to wake up
Subsequent loads are instant
```

---

## 📊 View Logs

**In Render Dashboard:**
1. Go to your Web Service
2. Click "Logs" tab
3. See real-time logs

**Check for:**
- Authentication success/failure
- Scan progress
- Database connections
- Errors

---

## 🎯 Next Steps

1. ✅ Push to GitHub
2. ✅ Deploy on Render
3. ✅ Add PostgreSQL
4. ✅ Set environment variables
5. ✅ Test a scan
6. ✅ Bookmark your URL

**Done! Your scanner is live and FREE forever!** 🚀

---

## 💰 Cost Summary

| Component | Cost |
|-----------|------|
| Web Service | FREE (750 hrs/month) |
| PostgreSQL | FREE (30-day renewal) |
| Bandwidth | FREE (under 100 GB) |
| **Total** | **$0/month - Forever** |

---

## 🆘 Need Help?

**Render Documentation:**
- https://render.com/docs

**Common Commands:**
```bash
# Check git status
git status

# Push changes
git add .
git commit -m "Update"
git push

# View Render logs (in dashboard)
# No CLI needed - use web interface
```

---

## 🎉 You're All Set!

Your EMA9 Pullback Scanner is ready to deploy to Render.com for **FREE FOREVER**!

**Ready to deploy? Follow the steps above!** 🚀
