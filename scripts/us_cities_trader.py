#!/usr/bin/env python3
"""
US Cities Weather Trader - Filter to US cities only
"""
import os
import sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

import json
import re
from datetime import datetime, timedelta
from gatherer.sources.openmeteo import OpenMeteoGatherer
from modeler.predictive_model_v3 import WeatherPredictorV3
from evaluator.trade_evaluator_v3_test import TradeEvaluatorV3Test

# US Cities only
US_CITIES = {
    'new york': (40.71, -74.01), 'nyc': (40.71, -74.01),
    'chicago': (41.88, -87.63), 'miami': (25.76, -80.19),
    'los angeles': (34.05, -118.24), 'la': (34.05, -118.24),
    'houston': (29.76, -95.37), 'dallas': (32.78, -96.80),
    'seattle': (47.61, -122.33), 'denver': (39.74, -104.99),
    'boston': (42.36, -71.06), 'atlanta': (33.75, -84.39),
    'phoenix': (33.45, -112.07), 'philadelphia': (39.95, -75.17),
    'san francisco': (37.77, -122.42), 'sf': (37.77, -122.42),
    'san diego': (32.72, -117.16), 'austin': (30.27, -97.74),
    'detroit': (42.33, -83.05), 'minneapolis': (44.98, -93.27),
    'washington dc': (38.91, -77.04), 'dc': (38.91, -77.04),
    'portland': (45.52, -122.68), 'las vegas': (36.17, -115.14),
    'nashville': (36.16, -86.78), 'new orleans': (29.95, -90.07),
    'cleveland': (41.50, -81.69), 'kansas city': (39.10, -94.58),
    'charlotte': (35.23, -80.84), 'indianapolis': (39.77, -86.16),
    'columbus': (39.96, -83.00), 'san antonio': (29.42, -98.49),
}

def extract_us_city(question: str):
    """Extract US city from question"""
    q_lower = question.lower()
    for city, coords in US_CITIES.items():
        if city in q_lower:
            return city, coords
    return None, None

def parse_threshold(question: str):
    """Parse temperature/snow threshold from question"""
    # Range patterns
    range_match = re.search(r'(\d+)[-–]\s*(\d+)', question)
    if range_match:
        low = int(range_match.group(1))
        high = int(range_match.group(2))
        return {'value': f"{low}-{high}", 'direction': 'between', 'low': low, 'high': high}
    
    # Single threshold
    num_match = re.search(r'(\d+)(?:\s*°|\s*degrees)', question)
    if num_match:
        value = int(num_match.group(1))
        # Determine direction
        q_lower = question.lower()
        if any(x in q_lower for x in ['below', 'under', 'or below', 'less than', '≤']):
            return {'value': value, 'direction': 'below'}
        elif any(x in q_lower for x in ['above', 'over', 'or above', 'more than', '≥']):
            return {'value': value, 'direction': 'above'}
        elif 'between' in q_lower or 'and' in q_lower:
            # Try to find second number
            nums = re.findall(r'\d+', q_lower)
            if len(nums) >= 2:
                return {'value': f"{nums[0]}-{nums[1]}", 'direction': 'between', 'low': int(nums[0]), 'high': int(nums[1])}
    
    return None

def run_us_cities_trading(test_mode=True, max_trades=5):
    """Run paper trading on US cities only"""
    print("=" * 60)
    print("🇺🇸 US CITIES WEATHER PAPER TRADING")
    print(f"Time: {datetime.now().strftime('%Y-%m-%d %H:%M %Z')}")
    print("=" * 60)
    
    # Load markets
    try:
        with open('data/markets/weather_full.json') as f:
            markets = json.load(f)
        print(f"\n📚 Loaded {len(markets)} total markets")
    except:
        print("❌ No market data found. Run scraper first.")
        return
    
    today = datetime.now().date()
    tomorrow = today + timedelta(days=1)
    
    # Find US city weather markets for today/tomorrow
    us_markets = []
    for m in markets:
        q = m.get('question', '')
        q_lower = q.lower()
        
        # Only temperature markets
        if 'temperature' not in q_lower:
            continue
        
        # Find US city
        city_name, coords = extract_us_city(q)
        if not city_name:
            continue
        
        end = m.get('end_date', '')
        if not end:
            continue
        
        try:
            end_date = datetime.fromisoformat(end.replace('Z', '+00:00')).date()
            # Include markets ending today or tomorrow
            if end_date not in [today, tomorrow]:
                continue
            
            prices = m.get('prices', {})
            yes_price = prices.get('Yes', {}).get('price', 0)
            no_price = prices.get('No', {}).get('price', 0)
            
            # Skip if one side is impossible
            if yes_price < 0.01 or yes_price > 0.99:
                continue
            
            threshold = parse_threshold(q)
            if not threshold:
                continue
            
            us_markets.append({
                'market': m,
                'city': city_name,
                'coords': coords,
                'end_date': end_date,
                'yes_price': yes_price,
                'no_price': no_price,
                'volume': float(m.get('volume', 0) or 0),
                'threshold': threshold
            })
        except:
            pass
    
    print(f"\n📊 Found {len(us_markets)} US city weather markets")
    
    if not us_markets:
        print("\n❌ No actionable US city markets for today/tomorrow")
        print("   Run: python src/scraper/weather_scraper.py")
        return
    
    # Show found markets
    print(f"\n📈 Markets with reasonable prices:")
    for m in us_markets[:10]:
        t = m['threshold']
        if t['direction'] == 'between':
            thresh_str = f"{t['low']}-{t['high']}°F"
        elif t['direction'] == 'below':
            thresh_str = f"≤{t['value']}°F"
        else:
            thresh_str = f"≥{t['value']}°F"
        
        print(f"  • {m['city'].title()}: {thresh_str}")
        print(f"    Ends: {m['end_date']} | Yes: {m['yes_price']:.2%} | Vol: ${m['volume']:,.0f}")
    
    print()
    
    # Initialize components
    gatherer = OpenMeteoGatherer()
    predictor = WeatherPredictorV3()
    evaluator = TradeEvaluatorV3Test(bankroll=1000.0)
    
    # Analyze and trade
    trades_executed = []
    trades_rejected = []
    
    # Sort by volume and take top
    top_markets = sorted(us_markets, key=lambda x: x['volume'], reverse=True)[:max_trades]
    
    print("🌤️ Analyzing top markets...")
    
    for item in top_markets:
        m = item['market']
        city = item['city']
        lat, lon = item['coords']
        target = item['end_date'].strftime('%Y-%m-%d')
        
        t = item['threshold']
        if t['direction'] == 'between':
            thresh_str = f"{t['low']}-{t['high']}°F"
        elif t['direction'] == 'below':
            thresh_str = f"≤{t['value']}°F"
        else:
            thresh_str = f"≥{t['value']}°F"
        
        print(f"\n📍 {city.title()}: {thresh_str} on {target}")
        print(f"   Market: Yes {item['yes_price']:.2%}")
        
        try:
            # Gather weather data
            climatology = gatherer.get_historical_for_date(lat, lon, item['end_date'].month, item['end_date'].day, years=20)
            forecast = gatherer.get_forecast(lat, lon, target)
            
            weather_data = {
                'climatology': climatology,
                'forecast': forecast
            }
            
            # Build market for predictor
            market = {
                'market_id': m.get('condition_id', 'unknown'),
                'question': m['question'],
                'threshold': item['threshold'],
                'target_date': target,
                'current_price_yes': item['yes_price'],
                'current_price_no': item['no_price']
            }
            
            # Run prediction
            pred = predictor.predict(market, weather_data)
            
            if 'error' in pred:
                print(f"   ⚠️ Prediction error: {pred['error']}")
                trades_rejected.append({'market': city, 'reason': 'pred_error'})
                continue
            
            model_prob = pred['prediction']['probability_yes']
            edge = pred['market_comparison']['edge_percent']
            
            print(f"   Forecast: {forecast.get('temp_max', 'N/A')}°F (avg)")
            print(f"   Model: {model_prob:.1%} | Edge: {abs(edge):.1%}")
            
            # Evaluate trade
            result = evaluator.evaluate(pred)
            
            if result['decision'] == 'EXECUTE':
                if test_mode:
                    result = evaluator.execute_paper_trade(result)
                    trades_executed.append(result)
                    print(f"   ✅ PAPER TRADE EXECUTED: {result['recommendation']['side']} ${result['recommendation']['size_usd']:.0f}")
                else:
                    print(f"   ✅ SIGNAL: {result['recommendation']['side']} ${result['recommendation']['size_usd']:.0f}")
                    trades_executed.append(result)
            else:
                print(f"   ⏭️ REJECTED: {result['reason']}")
                trades_rejected.append({'market': city, 'reason': result['reason']})
                
        except Exception as e:
            print(f"   ❌ Error: {str(e)[:50]}")
            trades_rejected.append({'market': city, 'reason': str(e)[:30]})
    
    # Summary
    print("\n" + "=" * 60)
    print("📊 SUMMARY")
    print("=" * 60)
    print(f"Markets analyzed: {len(top_markets)}")
    print(f"Trades executed: {len(trades_executed)}")
    print(f"Trades rejected: {len(trades_rejected)}")
    
    if trades_executed:
        total = sum(t['recommendation']['size_usd'] for t in trades_executed)
        print(f"\n💰 Executed Trades:")
        for i, t in enumerate(trades_executed, 1):
            rec = t['recommendation']
            risk = t['risk_analysis']
            print(f"\n{i}. {t['market_id'][:25]}...")
            print(f"   Side: {rec['side']} | Size: ${rec['size_usd']:.0f}")
            print(f"   Expected Net EV: {risk['net_edge_pct']:.1%}")
            print(f"   Net Profit: ${risk['net_ev']:.0f}")
            print(f"   Trade ID: {t['paper_trade']['paper_trade_id']}")
        print(f"\nTotal Exposure: ${total:.0f}")
        print("\n💡 To resolve tomorrow:\n   python src/evaluator/outcome_tracker.py resolve <trade_id> yes|no")
    
    # Save report
    report = {
        'date': today.isoformat(),
        'us_markets_found': len(us_markets),
        'analyzed': len(top_markets),
        'executed': len(trades_executed),
        'rejected': len(trades_rejected),
        'trades': trades_executed,
        'rejections': trades_rejected
    }
    
    report_file = 'data/positions/us_cities_report.json'
    with open(report_file, 'w') as f:
        json.dump(report, f, indent=2)
    print(f"\n💾 Report saved to {report_file}")
    
    return trades_executed


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument('--test', action='store_true', default=True, help='Test mode ($100 trades)')
    parser.add_argument('--max-trades', type=int, default=5, help='Max trades to execute')
    args = parser.parse_args()
    
    run_us_cities_trading(test_mode=args.test, max_trades=args.max_trades)
