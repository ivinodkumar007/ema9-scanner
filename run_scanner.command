#!/bin/bash
# EMA9 Pullback Scanner — macOS launcher (double-click to run)
cd "$(dirname "$0")"

# Create the virtual environment + install deps on first run
if [ ! -d "venv" ]; then
    echo "First run: setting up virtual environment..."
    python3 -m venv venv
    ./venv/bin/pip install --upgrade pip
    ./venv/bin/pip install flask pandas requests pyotp kiteconnect openpyxl
fi

./venv/bin/python app.py
