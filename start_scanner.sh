#!/bin/bash
# EMA9 Pullback Scanner - Quick Start
cd /Users/vinodkumar/Desktop/StockMarketApp

echo "=================================="
echo "  EMA9 Pullback Scanner"
echo "=================================="
echo ""

# Activate virtual environment
source venv/bin/activate

# Start the scanner
echo "Starting scanner on http://127.0.0.1:5037 ..."
echo "Press Ctrl+C to stop"
echo ""

python app.py
