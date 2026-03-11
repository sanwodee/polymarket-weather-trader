#!/usr/bin/env python3
"""
Backtest weather trading model on last 30 days
Compares model predictions to actual outcomes
"""
import json
import os
import sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

from datetime import datetime, timedelta
from gatherer.sources.openmeteo import OpenMeteoGatherer
from modeler.predictive_model_v4 import WeatherPredictorV4
import requests

# City coordinates
CITY_COORDS = {
    'new york': (40.71, -74.01), 'nyc': (40.71, -74.01),
    'chicago': (41.88, -87.63), 'miami': (25.76, -80.19),
    'los angeles': (34.05, -118.24), 'la': (34.05, -118.24),
    'houston': (29.76, -95.37), 'dallas': (32.78, -96.80),
    'seattle': (47.61, -122.33), 'denver': (39.74, -104.99),
    'boston': (42.36, -71.06), 'atlanta': (33.75, -84.39),
    'phoenix': (33.45, -112.07),
}

US_CITIES = {'new york', 'nyc', 'chicago', 'miami', 'los angeles', 'la',
    'houston', 'dallas', 'seattle', 'denver', 'boston', 'atlanta', 'phoenix'}

def extract_city(question):
    q_lower = question.lower()
    for city in CITY_COORDS.keys():
        if city in q_lower and city in US_CITIES:
            return city
    return None

def fetch_historical_max_temp(lat, lon, date):
    """Fetch actual max temperature for a date"""
    try:
        url = "https://archive-api.open-meteo.com/v1/archive"
        params = {
            'latitude': lat,
            'longitude': lon,
            'start_date': date.strftime('%Y-%m-%d'),
            'end_date': date.strftime('%Y-%m-%d'),
            'daily': 'temperature_2m_max',
            'temperature_unit': 'fahrenheit',
            'timezone': 'America/New_York'
        }
        response = requests.get(url, params=params, timeout=30)
        data = response.json()
        if 'daily' in data and 'temperature_2m_max' in data['daily']:
            return round(data['daily']['temperature_2m_max'][0], 1)
    except Exception as e:
        print(f"Error fetching weather: {e}")
    return None

def parse_threshold(question):
    """Parse threshold from question"""
    import re
    range_match = re.search(r'between\s+(\d+)[-–](\d+)', question.lower())
    if range_match:
        return {'type': 'range', 'low': int(range_match.group(1)), 'high': int(range_match.group(2))}
    
    # Extract numbers from questions like "76°F" or "80°F or higher"
    single_match = re.search(r'(\d+)(?:\s*°|\s*degrees)?\s*(F|°F)?', question)
    if single_match:
        temp = int(single_match.group(1))
        if 'or below' in question.lower() or 'or lower' in question.lower():
            return {'type': 'max', 'value': temp}
        elif 'or higher' in question.lower() or 'above' in question.lower():
            return {'type': 'min', 'value': temp}
    return None

def check_outcome(actual_temp, threshold):
    """Check if threshold was met"""
    if not threshold or actual_temp is None:
        return None
    if threshold['type'] == 'range':
        return threshold['low'] <= actual_temp <= threshold['high']
    elif threshold['type'] == 'min':
        return actual_temp >= threshold['value']
    elif threshold['type'] == 'max':
        return actual_temp <= threshold['value']
    return None

def get_forecast_for_date(lat, lon, target_date, forecast_date):
    """
    Get forecast as it would have appeared on forecast_date for target_date
    For 0-day: forecast_date == target_date
    For 1-day: forecast_date == target_date - 1 day
    """
    # For historical simulation, we'll use the actual forecast from Open-Meteo
    # This approximates what the forecast would have been
    try:
        days_ahead = (target_date - forecast_date).days
        
        # For backtesting, we fetch forecast as of forecast_date
        url = "https://api.open-meteo.com/v1/forecast"
        params = {
            'latitude': lat,
            'longitude': lon,
            'start_date': forecast_date.strftime('%Y-%m-%d'),
            'end_date': target_date.strftime('%Y-%m-%d'),
            'daily': 'temperature_2m_max',
            'temperature_unit': 'fahrenheit',
            'timezone': 'America/New_York'
        }
        response = requests.get(url, params=params, timeout=30)
        data = response.json()
        
        if 'daily' in data and 'temperature_2m_max' in data['daily']:
            # Return the forecast for target_date
            idx = (target_date - forecast_date).days
            if idx < len(data['daily']['temperature_2m_max']):
                return round(data['daily']['temperature_2m_max'][idx], 1)
    except Exception as e:
        print(f"Error fetching forecast: {e}")
    return None

def backtest_market(market, days_back=0):
    """
    Backtest a single market
    days_back: 0 for same-day forecast, 1 for 1-day ahead forecast
    """
    question = market.get('question', '')
    city = extract_city(question)
    
    if not city:
        return None, "Not a US city"
    
    end_date_str = market.get('end_date', '')
    if not end_date_str:
        return None, "No end date"
    
    try:
        end_date = datetime.fromisoformat(end_date_str.replace('Z', '+00:00')).date()
    except:
        return None, "Invalid date"
    
    # Only backtest dates in the past
    today = datetime.now().date()
    if end_date > today:
        return None, "Future date"
    
    # Get forecast date (today for 0-day, yesterday for 1-day)
    forecast_date = end_date - timedelta(days=days_back)
    
    # Fetch actual outcome
    lat, lon = CITY_COORDS[city]
    actual_temp = fetch_historical_max_temp(lat, lon, end_date)
    
    if actual_temp is None:
        return None, "Could not fetch actual weather"
    
    # Parse threshold
    threshold = parse_threshold(question)
    if not threshold:
        return None, "Could not parse threshold"
    
    # Check actual outcome
    actual_outcome = check_outcome(actual_temp, threshold)
    
    # Get historical forecast
    forecast_temp = get_forecast_for_date(lat, lon, end_date, forecast_date)
    
    if forecast_temp is None:
        return None, "Could not fetch forecast"
    
    # Predict using model
    gatherer = OpenMeteoGatherer()
    predictor = WeatherPredictorV4()
    
    climatology = gatherer.get_historical_for_date(lat, lon, end_date.month, end_date.day, years=20)
    
    weather_data = {
        'climatology': climatology,
        'forecast': {
            'forecast_date': end_date.strftime('%Y-%m-%d'),
            'high_temp': forecast_temp,
            'low_temp': forecast_temp - 15,  # Approximate
            'humidity': 50,
            'wind_speed': 5
        }
    }
    
    market_obj = {
        'market_id': market.get('condition_id', 'unknown'),
        'question': question,
        'threshold': threshold,
        'target_date': end_date.strftime('%Y-%m-%d'),
        'current_price_yes': market.get('prices', {}).get('Yes', {}).get('price', 0.5),
        'current_price_no': 1 - market.get('prices', {}).get('Yes', {}).get('price', 0.5)
    }
    
    prediction = predictor.predict(market_obj, weather_data)
    
    if 'error' in prediction:
        return None, f"Prediction error: {prediction['error']}"
    
    model_prob = prediction['prediction']['probability_yes']
    market_price = prediction['market_comparison']['market_price_yes']
    edge = prediction['market_comparison']['edge_percent']
    
    # Determine what model would predict
    if threshold['type'] == 'range':
        model_outcome = threshold['low'] <= forecast_temp <= threshold['high']
    elif threshold['type'] == 'min':
        model_outcome = forecast_temp >= threshold['value']
    else:  # max
        model_outcome = forecast_temp <= threshold['value']
    
    return {
        'date': end_date.strftime('%Y-%m-%d'),
        'city': city,
        'question': question[:60],
        'forecast_temp': forecast_temp,
        'actual_temp': actual_temp,
        'actual_outcome': actual_outcome,
        'model_outcome': model_outcome,
        'model_prob': model_prob,
        'market_price': market_price,
        'edge': edge,
        'correct': model_outcome == actual_outcome
    }, None

def run_backtest(days=30):
    """Run backtest for last N days"""
    print("=" * 80)
    print(f"🧪 BACKTEST: Last {days} Days")
    print("=" * 80)
    
    # Load markets
    market_file = 'data/markets/weather_full.json'
    if not os.path.exists(market_file):
        print(f"❌ Market file not found: {market_file}")
        return
    
    with open(market_file, 'r') as f:
        markets = json.load(f)
    
    today = datetime.now().date()
    cutoff = today - timedelta(days=days)
    
    # Filter markets in date range
    filtered_markets = []
    for m in markets:
        end_date_str = m.get('end_date', '')
        if not end_date_str:
            continue
        try:
            end_date = datetime.fromisoformat(end_date_str.replace('Z', '+00:00')).date()
            if cutoff <= end_date <= today:
                city = extract_city(m.get('question', ''))
                if city:
                    filtered_markets.append(m)
        except:
            continue
    
    print(f"📊 Found {len(filtered_markets)} markets in last {days} days")
    
    results = []
    errors = []
    
    for i, market in enumerate(filtered_markets, 1):
        print(f"\n[{i}/{len(filtered_markets)}] {market.get('question', 'Unknown')[:50]}...", end=' ')
        
        result, error = backtest_market(market, days_back=0)
        
        if result:
            results.append(result)
            status = "✅" if result['correct'] else "❌"
            print(f"{status} Forecast: {result['forecast_temp']}°F | Actual: {result['actual_temp']}°F")
        else:
            errors.append(error)
            print(f"⚠️ {error}")
    
    # Summary
    print(f"\n{'=' * 80}")
    print(f"📊 BACKTEST RESULTS (Last {days} days)")
    print(f"{'=' * 80}")
    
    if not results:
        print("❌ No results to analyze")
        return
    
    correct = sum(1 for r in results if r['correct'])
    total = len(results)
    accuracy = (correct / total * 100) if total else 0
    
    print(f"\nTotal markets tested: {total}")
    print(f"Correct predictions: {correct}")
    print(f"Incorrect predictions: {total - correct}")
    print(f"Accuracy: {accuracy:.1f}%")
    
    # Show breakdown by city
    print(f"\n📍 Accuracy by City:")
    city_stats = {}
    for r in results:
        city = r['city']
        if city not in city_stats:
            city_stats[city] = {'correct': 0, 'total': 0}
        city_stats[city]['total'] += 1
        if r['correct']:
            city_stats[city]['correct'] += 1
    
    for city, stats in sorted(city_stats.items(), key=lambda x: x[1]['total'], reverse=True):
        acc = (stats['correct'] / stats['total'] * 100) if stats['total'] else 0
        print(f"   {city.title()}: {stats['correct']}/{stats['total']} ({acc:.0f}%)")
    
    # Show error analysis
    print(f"\n❌ Errors encountered:")
    from collections import Counter
    error_counts = Counter(errors)
    for error, count in error_counts.most_common():
        print(f"   {count}x: {error}")
    
    # Show sample of incorrect predictions
    incorrect = [r for r in results if not r['correct']]
    if incorrect:
        print(f"\n📝 Sample Incorrect Predictions:")
        for r in incorrect[:5]:
            print(f"   {r['date']} {r['city']}: Forecast {r['forecast_temp']}°F, Actual {r['actual_temp']}°F")
            print(f"      Model: {r['model_outcome']}, Reality: {r['actual_outcome']}")
    
    return results

if __name__ == '__main__':
    results = run_backtest(days=30)
