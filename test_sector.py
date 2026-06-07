import requests 
import re 
r = requests.get("https://www.screener.in/company/FSL/", headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36", "Accept": "text/html"}, timeout=10) 
print("Status:", r.status_code) 
print("Length:", len(r.text)) 
print("Sector:", m.group(1).strip() if m else "NOT FOUND") 
