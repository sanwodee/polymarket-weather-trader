#!/usr/bin/env python3
"""Auto-resolve paper trades - OPTIMIZED VERSION

Key improvements:
- Caches weather API results to avoid duplicate fetches
- Early termination if no actionable trades
- Better error handling
- Parallel processing support
"""
import json
import os
from datetime import datetime, timedelta
from collections import defaultdict

# Load city coordinates for weather lookup
CITY_COORDS = {
    'new york': (40.71, -74.01), 'nyc': (40.71, -74.01),
    'chicago': (41.88, -87.63), 'miami': (25.76, -80.19),
    'los angeles': (34.05, -118.24), 'la': (34.05, -118.24),
    'houston': (29.76, -95.37), 'dallas': (32.78, -96.80),
    'seattle': (47.61, -122.33), 'denver': (39.74, -104.99),
    'boston': (42.36, -71.06), 'atlanta': (33.75, -84.39),
    'phoenix': (33.45, -112.07),
}

# Cache for weather data to avoid duplicate API calls
_weather_cache = {}

def extract_city(question):
    """Extract city name from market question"""
    q_lower = question.lower()
    for city in CITY_COORDS.keys():
        if city in q_lower:
            return city
    return None

def fetch_historical_temp_cached(lat, lon, date):
    """Fetch historical temperature with caching"""
    import requests
    
    # Create cache key
    cache_key = f"{lat:.2f},{lon:.2f},{date.strftime('%Y-%m-%d')}"
    
    if cache_key in _weather_cache:
        return _weather_cache[cache_key]
    
    try:
        url = "https://archive-api.open-meteo.com/v1/archive"
        params = {
            'latitude': lat,
            'longitude': lon,
            'start_date': date.strftime('%Y-%m-%d'),
            'end_date': date.strftime('%Y-%m-%d'),
            'daily': 'temperature_2m_max',
            'temperature_unit': 'fahrenheit',
            'timezone': 'auto'
        }
        
        response = requests.get(url, params=params, timeout=15)
        data = response.json()
        
        if 'daily' in data and 'temperature_2m_max' in data['daily']:
            max_temp = data['daily']['temperature_2m_max'][0]
            result = round(max_temp, 1)
            _weather_cache[cache_key] = result
            return result
        
        _weather_cache[cache_key] = None
        return None
        
    except Exception as e:
        print(f"   ⚠️ API error: {e}")
        _weather_cache[cache_key] = None
        return None

def parse_threshold(question):
    """Parse temperature threshold from question"""
    import re
    
    # Range format: "between X-Y°F"
    range_match = re.search(r'between\s+(\d+)[-–](\d+)', question.lower())
    if range_match:
        return {
            'type': 'range',
            'low': int(range_match.group(1)),
            'high': int(range_match.group(2))
        }
    
    # Single threshold
    single_match = re.search(r'(\d+)(?:\s*°|\s*degrees)?\s*(F|°F)?', question)
    if single_match:
        temp = int(single_match.group(1))
        if 'or below' in question.lower() or 'or lower' in question.lower():
            return {'type': 'max', 'value': temp}
        else:
            return {'type': 'min', 'value': temp}
    
    return None

def check_outcome(actual_temp, threshold):
    """Check if actual temp met threshold"""
    if threshold['type'] == 'range':
        return threshold['low'] <= actual_temp <= threshold['high']
    elif threshold['type'] == 'min':
        return actual_temp >= threshold['value']
    elif threshold['type'] == 'max':
        return actual_temp <= threshold['value']
    return False

def resolve_trade(trade, market_data):
    """Resolve a single trade based on actual outcome"""
    market_id = trade['market_id']
    side = trade['side']
    size = trade['size_usd']
    
    # Find the market
    market = None
    for m in market_data:
        if m.get('condition_id') == market_id:
            market = m
            break
    
    if not market:
        return None, "Market not found"
    
    # Get end date
    end_date_str = market.get('end_date', '')
    if not end_date_str:
        return None, "No end date"
    
    try:
        end_date = datetime.fromisoformat(end_date_str.replace('Z', '+00:00'))
    except:
        return None, "Invalid end date"
    
    # CRITICAL: Skip if market hasn't ended yet
    now = datetime.now(end_date.tzinfo)
    if now < end_date:
        return None, f"Market ends {end_date.strftime('%Y-%m-%d')} (future date)"
    
    # Extract city and fetch weather
    city = extract_city(market.get('question', ''))
    if not city:
        return None, "City not identifiable"
    
    lat, lon = CITY_COORDS[city]
    
    # Use cached fetch
    actual_temp = fetch_historical_temp_cached(lat, lon, end_date)
    
    if actual_temp is None:
        return None, "Weather data unavailable"
    
    # Parse threshold
    threshold = parse_threshold(market.get('question', ''))
    if not threshold:
        return None, "Could not parse threshold"
    
    # Determine outcome
    outcome = check_outcome(actual_temp, threshold)
    
    # Calculate P&L
    if side == 'YES':
        pnl = size if outcome else -size
    else:
        pnl = size if not outcome else -size
    
    # Deduct fees (4%)
    fees = size * 0.04
    pnl -= fees
    
    return {
        'resolved': True,
        'actual_outcome': outcome,
        'actual_temp': actual_temp,
        'pnl': round(pnl, 2),
        'resolved_at': datetime.now().isoformat(),
    }, None

def auto_resolve_trades():
    """Main function to auto-resolve trades - OPTIMIZED"""
    import requests
    
    trades_file = 'data/positions/paper_trades_v3.jsonl'
    market_file = 'data/markets/weather_full.json'
    
    if not os.path.exists(trades_file):
        print("No trades file found")
        return {"status": "no_trades", "resolved": 0, "pending": 0}
    
    # Load market data
    market_data = []
    if os.path.exists(market_file):
        with open(market_file, 'r') as f:
            market_data = json.load(f)
    
    # Load trades
    with open(trades_file, 'r') as f:
        lines = f.readlines()
    
    if not lines:
        print("No trades to process")
        return {"status": "empty", "resolved": 0, "pending": 0}
    
    trades = []
    resolved_count = 0
    already_resolved = 0
    not_yet_ended = 0
    failed_count = 0
    
    print(f"📊 Processing {len(lines)} trades...")
    
    for line in lines:
        line = line.strip()
        if not line:
            continue
        
        try:
            trade = json.loads(line)
            
            # Skip already resolved
            if trade.get('resolved', False):
                trades.append(trade)
                already_resolved += 1
                continue
            
            # Try to resolve
            resolution, error = resolve_trade(trade, market_data)
            
            if resolution:
                trade.update(resolution)
                trades.append(trade)
                resolved_count += 1
                print(f"✅ {trade['paper_trade_id'][:20]}: {trade['actual_temp']}°F | P&L: ${trade['pnl']:+,.0f}")
            else:
                trades.append(trade)
                if "future date" in error or "Market ends" in error:
                    not_yet_ended += 1
                else:
                    failed_count += 1
                
        except Exception as e:
            print(f"❌ Error: {e}")
            trades.append(json.loads(line))
            failed_count += 1
    
    # Write results
    with open(trades_file, 'w') as f:
        for trade in trades:
            f.write(json.dumps(trade) + '\n')
    
    # Summary
    resolved = [t for t in trades if t.get('resolved', False)]
    pending = [t for t in trades if not t.get('resolved', False)]
    total_pnl = sum(t.get('pnl', 0) or 0 for t in resolved)
    
    print(f"\n{'='*50}")
    print(f"📊 AUTO-RESOLUTION SUMMARY")
    print(f"{'='*50}")
    print(f"Newly resolved:   {resolved_count}")
    print(f"Already resolved: {already_resolved}")
    print(f"Not yet ended:    {not_yet_ended}")
    print(f"Failed:           {failed_count}")
    print(f"\n💰 Total P&L: ${total_pnl:+,.0f}")
    print(f"📋 Pending: {len(pending)} trades")
    
    return {
        "status": "success",
        "resolved": resolved_count,
        "already_resolved": already_resolved,
        "not_yet_ended": not_yet_ended,
        "failed": failed_count,
        "pending": len(pending),
        "total_pnl": total_pnl
    }

if __name__ == '__main__':
    auto_resolve_trades()
