# Railway Cron Setup Guide

## 📋 Overview

Your scanner will run automatically at:
- ✅ **10:00 AM IST** (Market morning session)
- ✅ **12:00 PM IST** (Mid-day check)
- ✅ **2:00 PM IST** (Afternoon session)

**Timezone**: Asia/Kolkata (IST, UTC+5:30)

---

## 🚀 Setup Steps

### Step 1: Deploy Main Web App

```bash
cd /Users/vinodkumar/Desktop/StockMarketApp
railway login
railway init
railway add postgresql
railway variables set UPSTOX_ANALYTICS_TOKEN="your_token_here"
railway up
```

### Step 2: Add Cron Service in Railway Dashboard

Railway cron jobs are set up via the **Dashboard**, not CLI:

1. **Go to your project**: https://railway.app
2. **Click "+ New"** → **"Empty Service"**
3. **Name it**: `ema9-scanner-cron`
4. **Connect to your GitHub repo**

### Step 3: Configure Cron Schedule

In Railway Dashboard for the cron service:

1. **Go to Settings tab**
2. **Find "Cron Schedule"**
3. **Set schedule**: `0 10,12,14 * * *`
   - This runs at 10 AM, 12 PM, and 2 PM UTC
   - For IST, use: `30 4,6,8 * * *` (4:30, 6:30, 8:30 AM UTC = 10, 12, 2 IST)

4. **Set Start Command**: `python cron_worker.py`

### Step 4: Set Environment Variables

For the cron service, add:
- `DATABASE_URL` (same as web app - Railway auto-provides)
- `UPSTOX_ANALYTICS_TOKEN` (your token)

---

## ⏰ Cron Schedule Explained

### Format: `minute hour day-of-month month day-of-week`

**For IST (UTC+5:30):**
```
30 4,6,8 * * *
```

Breakdown:
- `30` - 30th minute
- `4,6,8` - At 4, 6, and 8 AM UTC
- `* * *` - Every day, every month

**Converts to IST:**
- 4:30 AM UTC = 10:00 AM IST
- 6:30 AM UTC = 12:00 PM IST  
- 8:30 AM UTC = 2:00 PM IST

---

## 💡 Alternative: Use Railway CLI

If you prefer CLI, create separate cron services:

```bash
# Create cron service
railway service create --name ema9-cron

# Set start command
railway service ema9-cron --start-command "python cron_worker.py"

# Set cron schedule (runs 3x daily)
railway service ema9-cron --cron "30 4,6,8 * * *"

# Link to same codebase
railway link
```

---

## 🔧 Files Created

1. **cron_worker.py** - Standalone scan worker
   - Runs independently of web app
   - Connects to PostgreSQL
   - Executes full scan
   - Saves results to database

2. **app.py** - Web dashboard (unchanged)
   - Shows scan results
   - Allows manual scans
   - Export to Excel

---

## 💰 Cost Breakdown with Cron

### Web Service (Dashboard):
- **RAM**: 150 MB idle
- **Hours**: 24/day
- **Cost**: ~$0.72/day = **$21.60/month**

### Cron Service:
- **RAM**: 200 MB during scan
- **Runtime**: ~10 min × 3 scans = 30 min/day
- **Cost**: ~$0.02/day = **$0.60/month**

### Total: ~$22.20/month ❌

---

## ⚠️ Important: Better Approach

**Since Railway charges for uptime, you have 2 options:**

### Option A: Use Web Service Only (Simpler)
- Deploy just the web app
- Use **Railway's built-in scheduler** or **GitHub Actions**
- Web app stays on, cron runs separately
- **Cost**: ~$22/month

### Option B: Use Python Scheduler in Web App (Cheaper)
I can modify `app.py` to auto-run scans at scheduled times:
- No separate cron service needed
- Web app handles scheduling
- **Same cost**: ~$22/month

### Option C: Use GitHub Actions (Cheapest!)
- Free 2000 minutes/month
- Trigger scans via API
- **Cost**: $0 for scheduling + ~$22 for web app

---

## 🎯 My Recommendation

**Since you're paying ~$22/month anyway, use the simplest approach:**

### Keep Web App Running + Manual Scans

Your web app at `https://your-app.up.railway.app`:
- ✅ Click "Scan Now" button anytime
- ✅ View results anytime
- ✅ Export to Excel
- ✅ Access from anywhere

**No need for cron!** Just scan when you need it (takes 5-10 min).

---

## 📊 Comparison

| Approach | Monthly Cost | Complexity | Reliability |
|----------|-------------|------------|-------------|
| Manual scans (web UI) | ~$22 | Low | High |
| Railway cron | ~$23 | Medium | High |
| GitHub Actions + API | ~$22 | High | Medium |
| **Local (your Mac)** | **$0** | **Low** | **High** |

---

## 🤔 Final Decision

**Would you like to:**

1. **Deploy with cron** (~$23/month) - I'll guide you through Railway dashboard setup
2. **Deploy web app only** (~$22/month) - Manual scans when needed
3. **Keep local** (FREE) - Already working perfectly
4. **Look at free alternatives** (Render.com, Fly.io with free tiers)

What's your preference?
