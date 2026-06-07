"""
WSGI entry point for Vercel serverless deployment
"""
from app import app

# Vercel expects a variable named 'app' or to import it
if __name__ == "__main__":
    app.run()
