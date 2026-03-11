#!/usr/bin/env python3
"""Quick check for tomorrow's weather markets"""
import json
from datetime import datetime, timedelta

target_date = (datetime.now() + timedelta(days=1)).strftime('%Y-%m-%d')
print(f"🔍 Checking for markets closing on: {target_date}")

try:
    with open('data/markets/weather_full.json') as f:
        markets = json.load(f)
    
    count = 0
    us_cities = {'new york', 'nyc', 'chicago', 'miami', 'los angeles', 'la', 
                 'houston', 'dallas', 'seattle', 'denver', 'boston', 'atlanta', 'phoenix'}
    
    for m in markets:
        end = m.get('end_date', '')
        q = m.get('question', '').lower()
        if not end:
            continue
        try:
            end_date = datetime.fromisoformat(end.replace('Z', '+00:00')).strftime('%Y-%m-%d')
            if end_date == target_date:
                # Check if US city
                is_us = any(city in q for city in us_cities)
                if is_us and 'temperature' in q:
                    prices = m.get('prices', {})
                    yes_price = prices.get('Yes', {}).get('price', 0)
                    if 0.05 < yes_price < 0.95:
                        count += 1
                        prices = m.get('prices', {})
                        print(f"\n{count}. {m['question'][:60]}...")
                        print(f"   Yes: {prices.get('Yes', {}).get('price', 0):.2f}")
        except:
            pass
    
    print(f"\n{'='*60}")
    print(f"Total US weather markets for {target_date}: {count}")
    print(f"File last updated: Check data/markets/weather_full.json")
    
except FileNotFoundError:
    print("❌ No market data file found!")
except Exception as e:
    print(f"❌ Error: {e}")