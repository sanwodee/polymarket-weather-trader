#!/usr/bin/env python3
"""
Analyze forecast accuracy by US city
Compare Open-Meteo forecasts vs actual observed temperatures
"""
import os
import sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

import json
import requests
from datetime import datetime, timedelta

# US Cities with coords
US_CITIES = {
    'Atlanta': (33.75, -84.39),
    'Dallas': (32.78, -96.80),
    'Los Angeles': (34.05, -118.24),
    'Chicago': (41.88, -87.63),
    'Miami': (25.76, -80.19),
    'New York': (40.71, -74.01),
    'Seattle': (47.61, -122.33),
    'Denver': (39.74, -104.99),
}

def get_actual_temperature(lat, lon, date_str):
    """Fetch actual observed temperature from Open-Meteo archive"""
    try:
        # Open-Meteo archive API for historical data
        url = f"https://archive-api.open-meteo.com/v1/archive"
        params = {
            'latitude': lat,
            'longitude': lon,
            'start_date': date_str,
            'end_date': date_str,
            'daily': 'temperature_2m_max',
            'timezone': 'auto'
        }
        resp = requests.get(url, params=params, timeout=30)
        data = resp.json()
        if 'daily' in data and 'temperature_2m_max' in data['daily']:
            # Convert from Celsius to Fahrenheit
            celsius = data['daily']['temperature_2m_max'][0]
            fahrenheit = celsius * 9/5 + 32
            return round(fahrenheit, 1)
    except Exception as e:
        print(f"Error fetching actual temp: {e}")
    return None

def analyze_city_accuracy():
    print("="*70)
    print("🌡️ US CITY FORECAST ACCURACY ANALYSIS")
    print("="*70)
    print()
    print("Checking forecast vs actual for recent dates...")
    print()
    
    # Dates to analyze
    dates_to_check = [
        (datetime.now() - timedelta(days=3)).strftime('%Y-%m-%d'),
        (datetime.now() - timedelta(days=2)).strftime('%Y-%m-%d'),
        (datetime.now() - timedelta(days=1)).strftime('%Y-%m-%d'),
    ]
    
    results = {}
    
    for city_name, (lat, lon) in US_CITIES.items():
        print(f"\n📍 {city_name}:")
        print("-"*50)
        
        city_errors = []
        
        for date_str in dates_to_check:
            # Get forecast from cached weather data
            forecast_file = f"data/weather/{lat:.4f}_{lon:.4f}_{date_str}.json"
            forecast_temp = None
            
            if os.path.exists(forecast_file):
                try:
                    with open(forecast_file) as f:
                        fcast_data = json.load(f)
                        # Open-Meteo stores in Celsius, convert
                        if 'daily' in fcast_data and 'temperature_2m_max' in fcast_data['daily']:
                            celsius = fcast_data['daily']['temperature_2m_max'][0]
                            forecast_temp = round(celsius * 9/5 + 32, 1)
                except:
                    pass
            
            # Get actual temperature
            actual_temp = get_actual_temperature(lat, lon, date_str)
            
            if forecast_temp and actual_temp:
                error = abs(forecast_temp - actual_temp)
                city_errors.append(error)
                status = "✅" if error < 5 else "⚠️" if error < 10 else "❌"
                print(f"  {date_str}: Forecast {forecast_temp:.1f}°F → Actual {actual_temp:.1f}°F | Error: {error:.1f}°F {status}")
            elif forecast_temp:
                print(f"  {date_str}: Forecast {forecast_temp:.1f}°F → Actual: (pending)")
            else:
                print(f"  {date_str}: No forecast data available")
        
        if city_errors:
            avg_error = sum(city_errors) / len(city_errors)
            results[city_name] = {
                'avg_error': avg_error,
                'errors': city_errors,
                'samples': len(city_errors)
            }
            print(f"  Average Error: {avg_error:.1f}°F")
    
    # Summary rankings
    print("\n" + "="*70)
    print("📊 FORECAST ACCURACY RANKINGS")
    print("="*70)
    print()
    
    ranked = sorted(results.items(), key=lambda x: x[1]['avg_error'])
    
    for i, (city, data) in enumerate(ranked, 1):
        avg_err = data['avg_error']
        samples = data['samples']
        
        if avg_err < 3:
            rating = "🟢 Excellent"
        elif avg_err < 5:
            rating = "🟡 Good"
        elif avg_err < 8:
            rating = "🟠 Fair"
        else:
            rating = "🔴 Poor"
        
        print(f"{i}. {city:15s} | Avg Error: {avg_err:5.1f}°F | {rating} ({samples} days)")
    
    print()
    print("INTERPRETATION:")
    print("  🟢 < 3°F: High confidence trades OK")
    print("  🟡 3-5°F: Standard edge requirements")
    print("  🟠 5-8°F: Require larger margins, skip narrow ranges")
    print("  🔴 > 8°F: Avoid or require massive edges (15%+)")
    
    return results

if __name__ == "__main__":
    analyze_city_accuracy()
