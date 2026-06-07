# Web service (dashboard - always on)
web: gunicorn app:app --timeout 600 --workers 1

# Cron worker (runs scheduled scans)
# Note: Railway cron is configured in railway.json, not here
