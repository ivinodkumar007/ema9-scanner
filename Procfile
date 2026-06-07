# Web service (dashboard - always on)
# Increased timeout to 900 seconds (15 minutes) for long scans
web: gunicorn app:app --workers 2 --timeout 900 --keep-alive 5 --graceful-timeout 30
