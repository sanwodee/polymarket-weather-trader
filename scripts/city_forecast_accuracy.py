#!/usr/bin/env python3
"""
Forecast Accuracy Analysis - Compare cached forecasts to actuals
"""
import os
import json
import requests
from datetime import datetime, timedelta

US_CITIES = {
    'Atlanta': (33.75, -84.39),
    'Dallas': (32.78, -96.80),
    'Los Angeles': (34.05, -118.24),
    'Chicago': (41.88, -87.63),
    'Miami': (25.76, -80.19),
    'New York': (40.71, -74.01),
    'Houston': (29.76, -95.37),
    'Seattle': (47.61, -122.33),
}

def get_actual_temp(lat, lon, date_str):
    """Get actual temp from Open-Meteo archive"""
    try:
        url = 'https://archive-api.open-meteo.com/v1/archive'
        params = {
            'latitude': lat, 'longitude': lon,
            'start_date': date_str, 'end_date': date_str,
            'daily': 'temperature_2m_max', 'timezone': 'auto'
        }
        resp = requests.get(url, params=params, timeout=30)
        data = resp.json()
        if 'daily' in data and data['daily']['temperature_2m_max']:
            c = data['daily']['temperature_2m_max'][0]
            return round(c * 9/5 + 32, 1)
    except:
        pass
    return None

def get_cached_forecast(lat, lon, date_str):
    """Get forecast from cached file"""
    fname = f"data/weather/{lat:.4f}_{lon:.4f}_{date_str}.json"
    if os.path.exists(fname):
        try:
            with open(fname) as f:
                d = json.load(f)
                return d.get('temp_max')
        except:
            pass
    return None

print("="*70)
print("🌡️ US CITY FORECAST ACCURACY (Feb 24-26)")
print("="*70)
print()

dates = ['2026-02-24', '2026-02-25', '2026-02-26']
results = {}

for city, (lat, lon) in US_CITIES.items():
    errors = []
    print(f"\n📍 {city}:")
    print("-"*50)
    
    for d in dates:
        forecast = get_cached_forecast(lat, lon, d)
        actual = get_actual_temp(lat, lon, d)
        
        if forecast and actual:
            error = abs(forecast - actual)
            errors.append(error)
            status = "✅" if error < 5 else "⚠️" if error < 10 else "❌"
            print(f"  {d}: {forecast:.1f}°F → {actual:.1f}°F | Err: {error:.1f}°F {status}")
        elif forecast:
            print(f"  {d}: Forecast {forecast:.1f}°F → Actual: (fetching...)")
        else:
            print(f"  {d}: No data")
    
    if errors:
        avg = sum(errors)/len(errors)
        results[city] = avg
        print(f"  → Avg Error: {avg:.1f}°F")

# Rankings
print("\n" + "="*70)
print("📊 CITY ACCURACY RANKINGS (Lower = Better)")
print("="*70)
print()

ranked = sorted(results.items(), key=lambda x: x[1])
for i, (city, err) in enumerate(ranked, 1):
    if err < 3:
        r = "🟢 Excellent"
    elif err < 5:
        r = "🟡 Good"
    elif err < 8:
        r = "🟠 Fair"
    else:
        r = "🔴 Poor"
    print(f"{i}. {city:15s} | {err:5.1f}°F | {r}")

print()
print("STRATEGY BY CITY:")
print("  🟢 <3°F: Standard trading OK")
print("  🟡 3-5°F: OK, require 8%+ edge")
print("  🟠 5-8°F: Avoid 2°F ranges, 10%+ edge required")
print("  🔴 >8°F: Require 15%+ edge or skip")

# Show worst performers
print()
print("⚠️ CITIES TO WATCH:")
for city, err in ranked:
    if err > 8:
        print(f"  • {city}: High forecast error ({err:.1f}°F) — expect volatility")
