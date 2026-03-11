#!/usr/bin/env python3
"""
US Temperature Paper Trade - Targets US city temperature markets
"""
import os
import sys
import json
from datetime import datetime

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

from gatherer.sources.openmeteo import OpenMeteoGatherer
from modeler.predictive_model_v2 import WeatherPredictorV2
from evaluator.trade_evaluator_v2 import TradeEvaluatorV2

def load_weather_markets(filepath='data/markets/weather_full.json'):
    if not os.path.exists(filepath):
        return []
    with open(filepath, 'r') as f:
        return json.load(f)

def is_us_city(question):
    """Check if question mentions a US city"""
    q = question.lower()
    us_cities = ['new york', 'chicago', 'miami', 'atlanta', 'dallas', 'seattle', 
                 'los angeles', 'houston', 'boston', 'denver', 'nyc']
    return any(city in q for city in us_cities)

def extract_us_location(question):
    """Extract US city coordinates"""
    q = question.lower()
    cities = {
        'new york': ('New York City', 40.71, -74.01),
        'nyc': ('New York City', 40.71, -74.01),
        'chicago': ('Chicago', 41.88, -87.63),
        'miami': ('Miami', 25.76, -80.19),
        'atlanta': ('Atlanta', 33.75, -84.39),
        'dallas': ('Dallas', 32.78, -96.80),
        'seattle': ('Seattle', 47.61, -122.33),
        'los angeles': ('Los Angeles', 34.05, -118.24),
        'houston': ('Houston', 29.76, -95.37),
        'boston': ('Boston', 42.36, -71.06),
        'denver': ('Denver', 39.74, -104.99),
    }
    for key, (name, lat, lon) in cities.items():
        if key in q:
            return {'city': name, 'lat': lat, 'lon': lon, 'country': 'US'}
    return None

def extract_threshold_temp(question):
    """Extract temp threshold"""
    import re
    q = question.lower()
    
    # Look for temperature ranges
    patterns = [
        r'(\d+)[°\s]*f',
        r'between\s+(\d+)[-–]\d+',
        r'(\d+)\s*°',
    ]
    
    for pattern in patterns:
        match = re.search(pattern, q)
        if match:
            val = int(match.group(1))
            direction = 'above' if 'or higher' in q or 'above' in q or 'higher' in q else 'below'
            return {'value': val, 'unit': 'F', 'direction': direction}
    return None

def run_pipeline(bankroll=100000.0, min_edge=0.07, max_trades=5):
    print("=" * 60)
    print("🇺🇸 US TEMPERATURE MARKET PAPER TRADING")
    print("=" * 60)
    print(f"Bankroll: ${bankroll:,.0f}")
    print(f"Min Edge: {min_edge:.0%}")
    print(f"Max Trades: {max_trades}")
    print("=" * 60)
    print()
    
    # Load all markets
    print("📚 Loading markets...")
    markets = load_weather_markets()
    
    # Filter to US temperature markets
    us_temp_markets = []
    for m in markets:
        q = m.get('question', '').lower()
        if 'highest temperature' in q and is_us_city(q):
            if m.get('prices') and m.get('end_date'):
                m['location'] = extract_us_location(q)
                m['threshold'] = extract_threshold_temp(q)
                m['target_date'] = m['end_date'].split('T')[0] if m.get('end_date') else None
                if m['location'] and m['threshold']:
                    us_temp_markets.append(m)
    
    print(f"✅ Found {len(us_temp_markets)} US temperature markets")
    print()
    
    if not us_temp_markets:
        print("❌ No US temperature markets found")
        return []
    
    # Show sample
    print("📍 Sample markets:")
    for m in us_temp_markets[:5]:
        prices = m.get('prices', {})
        yes_p = prices.get('Yes', {}).get('price', 'N/A')
        print(f"  • {m['location']['city']}: {m['threshold']['value']}°F ({yes_p})")
    print()
    
    # Gather weather data
    print("🌤️ Gathering Open-Meteo data...")
    gatherer = OpenMeteoGatherer()
    
    markets_with_data = []
    for market in us_temp_markets[:max_trades * 2]:
        try:
            loc = market['location']
            thresh = market['threshold']
            date = market['target_date']
            
            print(f"   📍 {loc['city']}: {thresh['direction']} {thresh['value']}°F on {date}")
            
            # Parse date
            year, month, day = date.split('-')
            month, day = int(month), int(day)
            
            # Get climatology
            climatology = gatherer.get_historical_for_date(
                loc['lat'], loc['lon'], month, day, years=20
            )
            
            if climatology.get('years_available', 0) < 10:
                print(f"      ⚠️ Insufficient data ({climatology.get('years_available', 0)} years)")
                continue
            
            clim_prob = gatherer.calculate_threshold_probability(
                climatology, thresh['value'], thresh['direction']
            )
            
            forecast = gatherer.get_forecast(loc['lat'], loc['lon'], date)
            
            weather_data = {
                'climatology': {
                    **climatology, 
                    'baseline_probability_combined': clim_prob.get('baseline_probability_empirical', 0.3)
                },
                'forecast': forecast
            }
            
            markets_with_data.append({'market': market, 'weather_data': weather_data})
            print(f"      ✅ {climatology.get('years_available', 0)} years data")
            
        except Exception as e:
            print(f"      ❌ Error: {e}")
            continue
    
    print(f"✅ Gathered data for {len(markets_with_data)} markets\n")
    
    if not markets_with_data:
        return []
    
    # Run predictions
    print("🤖 Running predictive models...")
    predictor = WeatherPredictorV2()
    
    predictions = []
    for item in markets_with_data:
        try:
            market = item['market']
            prices = market.get('prices', {})
            
            pred_input = {
                'market_id': market.get('condition_id', 'unknown'),
                'question': market['question'],
                'location': market['location'],
                'threshold': market['threshold'],
                'target_date': market['target_date'],
                'current_price_yes': prices.get('Yes', {}).get('price', 0.5),
                'current_price_no': prices.get('No', {}).get('price', 0.5),
            }
            
            pred = predictor.predict(pred_input, item['weather_data'])
            predictions.append(pred)
            
            edge_pct = pred['market_comparison']['edge_percent'] * 100
            print(f"   📊 {market['question'][:45]}...")
            print(f"      Market: {pred['market_comparison']['market_price_yes']:.3f} | Model: {pred['prediction']['probability_yes']:.3f} | Edge: {edge_pct:.1f}%")
            
        except Exception as e:
            print(f"      ❌ Error: {e}")
    
    print(f"✅ Generated {len(predictions)} predictions\n")
    
    if not predictions:
        return []
    
    # Evaluate and trade
    print("💰 Evaluating trades...")
    evaluator = TradeEvaluatorV2(bankroll=bankroll, use_maker_orders=False)
    
    trades_executed = []
    
    for pred in predictions:
        try:
            pred['market_location'] = {'city': pred.get('location', {}).get('city', 'Unknown')}
            result = evaluator.evaluate(pred)
            
            if result['decision'] == 'EXECUTE':
                result = evaluator.execute_paper_trade(result)
                trades_executed.append(result)
                
                rec = result['recommendation']
                print(f"\n   ✅ PAPER TRADE:")
                print(f"      {result['question'][:50]}...")
                print(f"      {rec['side']} ${rec['size_usd']:,.0f} ({result['paper_trade']['paper_trade_id']})")
                print(f"      Edge: {result['risk_analysis']['edge_pct']*100:.1f}%")
                
                if len(trades_executed) >= max_trades:
                    print(f"\n   🎯 Max trades reached")
                    break
            else:
                print(f"   ⏭️  {result['reason']}")
                
        except Exception as e:
            print(f"   ❌ Error: {e}")
    
    # Summary
    print()
    print("=" * 60)
    print("📋 SUMMARY")
    print("=" * 60)
    print(f"US markets found: {len(us_temp_markets)}")
    print(f"Markets analyzed: {len(markets_with_data)}")
    print(f"Predictions: {len(predictions)}")
    print(f"Paper trades: {len(trades_executed)}")
    
    if trades_executed:
        total = sum(t['recommendation']['size_usd'] for t in trades_executed)
        print(f"Total exposure: ${total:,.0f}")
        for t in trades_executed:
            print(f"  • {t['recommendation']['side']} ${t['recommendation']['size_usd']:,.0f} - {t['question'][:40]}...")
    
    print("=" * 60)
    return trades_executed

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument('--bankroll', type=float, default=100000.0)
    parser.add_argument('--min-edge', type=float, default=0.07)
    parser.add_argument('--max-trades', type=int, default=5)
    args = parser.parse_args()
    
    trades = run_pipeline(
        bankroll=args.bankroll,
        min_edge=args.min_edge,
        max_trades=args.max_trades
    )
