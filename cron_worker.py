#!/usr/bin/env python3
"""
Cron Worker for EMA9 Pullback Scanner
Runs scheduled scans on Railway without keeping the web app running 24/7
"""

import os
import sys
import time
from datetime import datetime

# Add current directory to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from config import *
from auth import get_kite
from app import run_scan, init_db

def main():
    """Run a scheduled scan."""
    print("="*70)
    print(f"  CRON SCAN STARTED: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("="*70)
    
    # Initialize database
    init_db()
    
    # Authenticate
    print("\n  Authenticating with Upstox...")
    kite = get_kite()
    
    if not kite:
        print("  ✗ Authentication failed!")
        sys.exit(1)
    
    print("  ✓ Authenticated\n")
    
    # Run scan (console mode = True)
    start_time = time.time()
    run_scan(console=True)
    elapsed = time.time() - start_time
    
    print(f"\n{'='*70}")
    print(f"  CRON SCAN COMPLETED in {elapsed:.1f} seconds")
    print(f"  Results saved to database")
    print(f"{'='*70}\n")

if __name__ == "__main__":
    main()
