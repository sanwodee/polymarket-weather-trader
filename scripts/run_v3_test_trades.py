#!/usr/bin/env python3
"""
Run 5 V3 test trades on fresh weather markets
"""
import os
import sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

import json
from datetime import datetime
from gatherer.sources.openmeteo import OpenMeteoGatherer
from modeler.predictive_model_v3 import WeatherPredictorV3
from evaluator.trade_evaluator_v3_test import TradeEvaluatorV3Test

print("=" * 60)
print("🧪 V3 Test Trades - $100/trade")
print("=" * 60)

# Load fresh markets
with open('data/markets/weather_full.json') as f:
    markets = json.load(f)

today = datetime.now().date()

# Filter active weather markets
active = []
for m in markets:
    q = m.get('question', '').lower()
    if 'temperature' not in q and 'snow' not in q and 'rain' not in q:
        continue
    
    end = m.get('end_date', '')
    if not end:
        continue
    
    try:
        end_date = datetime.fromisoformat(end.replace('Z', '+00:00')).date()
        if end_date < today:
            continue
        
        prices = m.get('prices', {})
        yes_price = prices.get('Yes', {}).get('price', 0)
        if yes_price > 0.01:  # Skip markets where YES is impossible
            active.append({
                'market': m,
                'end_date': end_date,
                'yes_price': yes_price
            })
    except:
        pass

print(f"Found {len(active)} active weather markets")

# Select top 10 by liquidity
top_markets = sorted(active, key=lambda x: float(x['market'].get('volume', 0) or 0), reverse=True)[:10]

print(f"\n📊 Analyzing top {len(top_markets)} markets...")

# Initialize components
gatherer = OpenMeteoGatherer()
predictor = WeatherPredictorV3()
evaluator = TradeEvaluatorV3Test(bankroll=500.0)

# Track results
trades_executed = []
trades_rejected = []

for item in top_markets[:5]:  # Test 5 markets
    m = item['market']
    q = m['question']
    
    print(f"\n📍 {q[:50]}...")
    
    # Extract location
    city_coords = {
        'new york': (40.71, -74.01),
        'nyc': (40.71, -74.01),
        'london': (51.51, -0.13),
        'seoul': (37.57, 126.98),
        'chicago': (41.88, -87.63),
        'miami': (25.76, -80.19),
        'dallas': (32.78, -96.80),
    }
    
    coords = None
    for city, (lat, lon) in city_coords.items():
        if city in q.lower():
            coords = (lat, lon)
            break
    
    if not coords:
        print("   ⚠️ No coordinates found")
        trades_rejected.append({'reason': 'no_coords', 'question': q[:50]})
        continue
    
    lat, lon = coords
    
    # Get date
    end_dt = item['end_date']
    target = end_dt.strftime('%Y-%m-%d')
    
    # Gather weather
    try:
        climatology = gatherer.get_historical_for_date(lat, lon, end_dt.month, end_dt.day, years=20)
        forecast = gatherer.get_forecast(lat, lon, target)
        
        weather_data = {
            'climatology': climatology,
            'forecast': forecast
        }
        
        # Parse threshold
        threshold = {'value': 0, 'direction': 'above', 'question': q}
        
        # Check for ranges
        import re
        range_match = re.search(r'(\d+)[-–](\d+)', q)
        if range_match:
            threshold['value'] = f"{range_match.group(1)}-{range_match.group(2)}"
            threshold['direction'] = 'between'
        else:
            # Single threshold
            num_match = re.search(r'(\d+)(?:\s*°|\s*degrees|\s*C|\s*F)?', q)
            if num_match:
                threshold['value'] = int(num_match.group(1))
                if 'below' in q.lower() or 'under' in q.lower():
                    threshold['direction'] = 'below'
        
        # Build market for predictor
        market = {
            'market_id': m.get('condition_id', 'unknown'),
            'question': q,
            'threshold': threshold,
            'target_date': target,
            'current_price_yes': item['yes_price'],
            'current_price_no': 1 - item['yes_price']
        }
        
        # Run prediction
        pred = predictor.predict(market, weather_data)
        
        if 'error' in pred:
            print(f"   ⚠️ Prediction error: {pred['error']}")
            trades_rejected.append({'reason': 'pred_error', 'question': q[:50]})
            continue
        
        model_prob = pred['prediction']['probability_yes']
        edge = pred['market_comparison']['edge_percent']
        
        print(f"   Market: {item['yes_price']:.2%} | Model: {model_prob:.2%} | Edge: {edge:.1%}")
        
        # Evaluate trade
        result = evaluator.evaluate(pred)
        
        if result['decision'] == 'EXECUTE':
            result = evaluator.execute_paper_trade(result)
            trades_executed.append(result)
            print(f"   ✅ EXECUTED: {result['recommendation']['side']} ${result['recommendation']['size_usd']:.0f}")
            print(f"      Trade ID: {result['paper_trade']['paper_trade_id']}")
        else:
            trades_rejected.append({'reason': result['reason'], 'question': q[:50]})
            print(f"   ⏭️ REJECTED: {result['reason']}")
            
    except Exception as e:
        print(f"   ❌ Error: {str(e)[:50]}")
        trades_rejected.append({'reason': str(e)[:30], 'question': q[:50]})

# Summary
print("\n" + "=" * 60)
print("📊 Test Results")
print("=" * 60)
print(f"Markets analyzed: {len(top_markets[:5])}")
print(f"Trades executed: {len(trades_executed)}")
print(f"Trades rejected: {len(trades_rejected)}")

if trades_executed:
    total = sum(t['recommendation']['size_usd'] for t in trades_executed)
    print(f"\nExecuted Trades:")
    for t in trades_executed:
        print(f"  • {t['market_id'][:20]}: {t['recommendation']['side']} ${t['recommendation']['size_usd']:.0f}")
        print(f"    ID: {t['paper_trade']['paper_trade_id']} | EV: {t['risk_analysis']['net_edge_pct']:.1%}")
    print(f"\nTotal Exposure: ${total:.0f}")

# Save summary
summary = {
    'test_date': datetime.now().isoformat(),
    'total_analyzed': 5,
    'executed': len(trades_executed),
    'rejected': len(trades_rejected),
    'executed_trades': trades_executed,
    'rejected_reasons': trades_rejected
}

with open('data/positions/v3_live_test_results.json', 'w') as f:
    json.dump(summary, f, indent=2)

print("\n💾 Saved to data/positions/v3_live_test_results.json")
