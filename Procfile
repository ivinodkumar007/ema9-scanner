# Web service (dashboard - always on)
# Using gevent for better async handling on Render
web: gunicorn app:app --worker-class gevent --workers 2 --timeout 600 --keep-alive 5
