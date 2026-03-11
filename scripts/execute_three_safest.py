#!/usr/bin/env python3
"""
Execute 3 safest $500 trades for tomorrow
"""
import os
import sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

import json
import re
from datetime import datetime, timedelta
from gatherer.sources.openmeteo import OpenMeteoGatherer
from modeler.predictive_model_v4 import WeatherPredictorV4
from evaluator.trade_evaluator_v3 import TradeEvaluatorV3

CITIES = {
    'chicago': (41.88, -87.63), 'miami': (25.76, -80.19),
    'dallas': (32.78, -96.80), 'new york': (40.71, -74.01),
    'la': (34.05, -118.24), 'houston': (29.76, -95.37)
}

def extract_city(question):
    q = question.lower()
    for city in CITIES.keys():
        if city in q:
            return city
    return None

def run_safest_trades():
    """Find and execute 3 safest $500 trades"""
    print("=" * 70)
    print("🎯 FINDING 3 SAFEST $500 TRADES")
    print("=" * 70)
    
    with open('data/markets/weather_full.json') as f:
        markets = json.load(f)
    
    today = datetime.now().date()
    tomorrow = today + timedelta(days=1)
    
    gatherer = OpenMeteoGatherer()
    predictor = WeatherPredictorV4()
    evaluator = TradeEvaluatorV3(bankroll=50000.0)
    
    opportunities = []
    
    for m in markets:
        q = m.get('question', '').lower()
        city = extract_city(q)
        if not city:
            continue
        if 'temperature' not in q or 'highest' not in q:
            continue
        
        end = m.get('end_date', '')
        if not end:
            continue
        
        try:
            end_date = datetime.fromisoformat(end.replace('Z', '+00:00')).date()
            if end_date != tomorrow:
                continue
            
            prices = m.get('prices', {})
            yes_price = prices.get('Yes', {}).get('price', 0)
            if not (0.05 < yes_price < 0.95):
                continue
            
            lat, lon = CITIES[city]
            forecast = gatherer.get_forecast(lat, lon, tomorrow.strftime('%Y-%m-%d'))
            climatology = gatherer.get_historical_for_date(lat, lon, tomorrow.month, tomorrow.day, years=20)
            
            if not forecast or not climatology:
                continue
            
            forecast_high = forecast.get('temp_max', 0)
            
            # Parse threshold
            range_match = re.search(r'(\d+)[-\u2013](\d+)', m['question'])
            num_match = re.search(r'(\d+)', m['question'])
            
            if range_match:
                low, high = int(range_match.group(1)), int(range_match.group(2))
                threshold = {'value': f'{low}-{high}', 'direction': 'between'}
                mid = (low + high) / 2
                margin = abs(forecast_high - mid)
            elif num_match:
                val = int(num_match.group(1))
                direction = 'below' if 'below' in q or 'under' in q else 'above'
                threshold = {'value': val, 'direction': direction}
                margin = abs(forecast_high - val)
            else:
                continue
            
            market = {
                'market_id': m.get('condition_id', 'unknown'),
                'question': m['question'],
                'threshold': threshold,
                'target_date': tomorrow.strftime('%Y-%m-%d'),
                'current_price_yes': yes_price,
                'current_price_no': 1 - yes_price
            }
            
            weather_data = {'climatology': climatology, 'forecast': forecast}
            pred = predictor.predict(market, weather_data)
            
            if 'error' in pred:
                continue
            
            model_prob = pred['prediction']['probability_yes']
            edge = pred['market_comparison']['edge_percent']
            
            # Score = margin * |edge| (safest with best edge)
            safety_score = margin * abs(edge)
            
            opportunities.append({
                'city': city.title(),
                'market': market,
                'prediction': pred,
                'weather': weather_data,
                'margin': margin,
                'edge': edge,
                'abs_edge': abs(edge),
                'model_prob': model_prob,
                'market_price': yes_price,
                'forecast_high': forecast_high,
                'safety_score': safety_score,
                'side': pred['recommendation']['side']
            })
            
        except Exception as e:
            continue
    
    # Sort by safety score (highest margin * edge)
    opportunities.sort(key=lambda x: -x['safety_score'])
    
    print(f"\n📊 Analyzed {len(opportunities)} markets")
    print(f"Target: 3 safest trades\n")
    
    # Execute top 3
    trades_executed = []
    for i, opp in enumerate(opportunities[:3], 1):
        # Force trade with $500
        trade = {
            'market_id': opp['market']['market_id'],
            'question': opp['market']['question'],
            'decision': 'EXECUTE',
            'recommendation': {
                'side': opp['side'],
                'size_usd': 500.0,
                'shares': int(500 / opp['market_price']) if opp['side'] == 'YES' else int(500 / (1 - opp['market_price'])),
                'confidence': opp['prediction']['recommendation']['confidence']
            },
            'risk_analysis': {
                'margin': opp['margin'],
                'edge': opp['edge'],
                'forecast': opp['forecast_high']
            },
            'status': 'paper_executed',
            'evaluated_at': datetime.now().isoformat()
        }
        
        trades_executed.append(trade)
        
        print(f"✅ TRADE {i}: {opp['city']} | Closes {tomorrow}")
        print(f"   {opp['market']['question'][:50]}...")
        print(f"   Side: {opp['side']} | Size: $500")
        print(f"   Market: {opp['market_price']:.1%} | Model: {opp['model_prob']:.1%}")
        print(f"   Edge: {opp['edge']:+.1%} | Margin: {opp['margin']:.1f}°F")
        print(f"   Forecast High: {opp['forecast_high']}°F")
        print(f"   Safety Score: {opp['safety_score']:.1f}")
        print()
    
    # Summary
    print("=" * 70)
    print(f"📊 EXECUTED {len(trades_executed)} TRADES")
    print("=" * 70)
    total = sum(t['recommendation']['size_usd'] for t in trades_executed)
    print(f"Total Exposure: ${total:,.0f}")
    
    for t in trades_executed:
        margin = t['risk_analysis']['margin']
        edge = t['risk_analysis']['edge']
        print(f"\n  • {t['question'][:40]}...")
        print(f"    {t['recommendation']['side']} ${t['recommendation']['size_usd']:.0f} ({margin:.1f}°F margin, {edge:+.0%} edge)")
    
    # Save report
    report = {
        'date': today.isoformat(),
        'target_date': tomorrow.isoformat(),
        'time': datetime.now().isoformat(),
        'type': 'three_safest_500',
        'trades': trades_executed,
        'markets_analyzed': len(opportunities)
    }
    
    report_file = f"data/positions/safest_trades/{today}_3x500.json"
    os.makedirs(os.path.dirname(report_file), exist_ok=True)
    with open(report_file, 'w') as f:
        json.dump(report, f, indent=2)
    
    print(f"\n💾 Report saved: {report_file}")

if __name__ == "__main__":
    run_safest_trades()
