#!/usr/bin/env python3
"""
Execute top 3 US weather trades for Sunday March 1st
$500 each, live forecast + V4 model
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

# US Cities
US_CITIES = {
    'new york': (40.71, -74.01), 'nyc': (40.71, -74.01),
    'chicago': (41.88, -87.63), 'miami': (25.76, -80.19),
    'los angeles': (34.05, -118.24), 'la': (34.05, -118.24),
    'houston': (29.76, -95.37), 'dallas': (32.78, -96.80),
    'seattle': (47.61, -122.33), 'denver': (39.74, -104.99),
    'boston': (42.36, -71.06), 'atlanta': (33.75, -84.39),
    'phoenix': (33.45, -112.07), 'philadelphia': (39.95, -75.17),
}

def extract_us_city(question):
    q_lower = question.lower()
    for city, coords in US_CITIES.items():
        if city in q_lower:
            return city, coords
    return None, None

def parse_threshold(question):
    range_match = re.search(r'(\d+)[-–]\s*(\d+)', question)
    if range_match:
        low, high = int(range_match.group(1)), int(range_match.group(2))
        return {'value': f"{low}-{high}", 'direction': 'between', 'low': low, 'high': high}
    
    num_match = re.search(r'(\d+)(?:\s*°|\s*degrees)', question)
    if num_match:
        value = int(num_match.group(1))
        q_lower = question.lower()
        if any(x in q_lower for x in ['below', 'under', 'or below', 'less than', '≤']):
            return {'value': value, 'direction': 'below'}
        else:
            return {'value': value, 'direction': 'above'}
    return None

def run_march1_trades(trade_size=500, max_trades=3):
    print("="*70)
    print("🇺🇸 SUNDAY MARCH 1ST - TOP US WEATHER TRADES")
    print(f"Trade Size: ${trade_size} | Max Trades: {max_trades}")
    print(f"Time: {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    print("="*70)
    
    # Load markets
    with open('data/markets/weather_full.json') as f:
        markets = json.load(f)
    
    target_date = datetime.now().date() + timedelta(days=2)  # March 1
    print(f"\n📅 Target Date: {target_date} (Sunday, March 1)")
    print(f"📚 Total markets loaded: {len(markets)}")
    
    # Find US city markets for March 1
    us_markets = []
    for m in markets:
        q = m.get('question', '')
        if 'temperature' not in q.lower():
            continue
        
        city, coords = extract_us_city(q)
        if not city:
            continue
        
        end = m.get('end_date', '')
        if not end:
            continue
        
        try:
            end_date = datetime.fromisoformat(end.replace('Z', '+00:00')).date()
            if end_date != target_date:
                continue
            
            prices = m.get('prices', {})
            yes_price = prices.get('Yes', {}).get('price', 0)
            no_price = prices.get('No', {}).get('price', 0)
            volume = float(m.get('volume', 0) or 0)
            
            if yes_price < 0.01 or yes_price > 0.99:
                continue
            
            threshold = parse_threshold(q)
            if not threshold:
                continue
            
            us_markets.append({
                'market': m,
                'city': city,
                'coords': coords,
                'yes_price': yes_price,
                'no_price': no_price,
                'volume': volume,
                'threshold': threshold,
                'question': q
            })
        except:
            pass
    
    print(f"📊 US markets for March 1: {len(us_markets)}")
    
    if not us_markets:
        print("❌ No markets found")
        return
    
    # Initialize components
    gatherer = OpenMeteoGatherer()
    predictor = WeatherPredictorV4()
    evaluator = TradeEvaluatorV3(bankroll=10000)
    
    # Analyze all markets
    print("\n🌤️ Analyzing with live forecasts and V4 model...")
    opportunities = []
    
    for item in us_markets:
        m = item['market']
        city = item['city']
        lat, lon = item['coords']
        target = target_date.strftime('%Y-%m-%d')
        
        t = item['threshold']
        if t['direction'] == 'between':
            thresh_str = f"{t['low']}-{t['high']}°F"
        elif t['direction'] == 'below':
            thresh_str = f"≤{t['value']}°F"
        else:
            thresh_str = f"≥{t['value']}°F"
        
        try:
            climatology = gatherer.get_historical_for_date(lat, lon, target_date.month, target_date.day, years=20)
            forecast = gatherer.get_forecast(lat, lon, target)
            
            weather_data = {'climatology': climatology, 'forecast': forecast}
            
            market = {
                'market_id': m.get('condition_id', 'unknown'),
                'question': m['question'],
                'threshold': item['threshold'],
                'target_date': target,
                'current_price_yes': item['yes_price'],
                'current_price_no': item['no_price']
            }
            
            pred = predictor.predict(market, weather_data)
            
            if 'error' in pred:
                continue
            
            model_prob = pred['prediction']['probability_yes']
            edge = pred['market_comparison']['edge_percent']
            net_edge = pred['market_comparison'].get('net_edge_percent', edge * 0.92)
            
            result = evaluator.evaluate(pred)
            
            if result['decision'] == 'EXECUTE':
                opportunities.append({
                    'item': item,
                    'pred': pred,
                    'result': result,
                    'model_prob': model_prob,
                    'edge': edge,
                    'net_edge': net_edge,
                    'thresh_str': thresh_str,
                    'forecast': forecast
                })
        except Exception as e:
            pass
    
    print(f"✅ {len(opportunities)} markets meet edge criteria")
    
    if not opportunities:
        print("❌ No qualifying opportunities")
        return
    
    # Sort by absolute net edge
    opportunities.sort(key=lambda x: abs(x['net_edge']), reverse=True)
    
    # Execute top trades
    trades_executed = []
    
    print(f"\n💰 EXECUTING TOP {min(max_trades, len(opportunities))} $500 TRADES:")
    print("="*70)
    
    for i, opp in enumerate(opportunities[:max_trades], 1):
        item = opp['item']
        result = opp['result']
        city = item['city'].title()
        
        # Set trade size to $500
        result['recommendation']['size_usd'] = trade_size
        result['recommendation']['shares'] = trade_size
        
        trade_result = evaluator.execute_paper_trade(result)
        trades_executed.append(trade_result)
        
        rec = trade_result['recommendation']
        risk = trade_result['risk_analysis']
        
        print(f"\n{i}. 🌡️ {city} - {opp['thresh_str']}")
        print(f"   Forecast: {opp['forecast'].get('temp_max', 'N/A')}°F high")
        print(f"   Market: Yes {item['yes_price']:.2%} | Model: {opp['model_prob']:.1%}")
        print(f"   🎯 TRADE: {rec['side']} ${rec['size_usd']:.0f}")
        print(f"   Gross Edge: {opp['edge']:.1f}% | Net Edge: {risk['net_edge_pct']:.1f}%")
        print(f"   Expected Net Profit: ${risk['net_ev']:.0f}")
        print(f"   Market ID: {item['market'].get('condition_id', 'unknown')[:25]}...")
        print(f"   Trade ID: {trade_result['paper_trade']['paper_trade_id']}")
    
    # Summary
    print("\n" + "="*70)
    print("📊 EXECUTION SUMMARY")
    print("="*70)
    print(f"Markets Analyzed: {len(us_markets)}")
    print(f"Qualifying Opportunities: {len(opportunities)}")
    print(f"Trades Executed: {len(trades_executed)}")
    
    if trades_executed:
        total = sum(t['recommendation']['size_usd'] for t in trades_executed)
        total_ev = sum(t['risk_analysis']['net_ev'] for t in trades_executed)
        
        print(f"\nTotal Capital Deployed: ${total:.0f}")
        print(f"Total Expected Net Profit: ${total_ev:.0f}")
        
        print(f"\n📋 Active Paper Trades:")
        for i, t in enumerate(trades_executed, 1):
            rec = t['recommendation']
            mkt = t['market_id'][:35]
            print(f"  {i}. {rec['side']} ${rec['size_usd']:.0f} - {mkt}...")
        
        print(f"\n⏰ Settles: Sunday, March 1, 2026")
        print(f"\n💡 Check results Monday morning:")
        print(f"   .venv/bin/python src/evaluator/outcome_tracker.py")
    
    # Save report
    report = {
        'date': datetime.now().isoformat(),
        'target_date': target_date.isoformat(),
        'us_markets_found': len(us_markets),
        'opportunities': len(opportunities),
        'trades_executed': len(trades_executed),
        'total_deployed': sum(t['recommendation']['size_usd'] for t in trades_executed),
        'total_expected_ev': sum(t['risk_analysis']['net_ev'] for t in trades_executed),
        'trades': trades_executed
    }
    
    report_file = f'data/positions/march1_us_trades.json'
    os.makedirs(os.path.dirname(report_file), exist_ok=True)
    with open(report_file, 'w') as f:
        json.dump(report, f, indent=2)
    print(f"\n💾 Report saved: {report_file}")
    
    return trades_executed

if __name__ == "__main__":
    run_march1_trades(trade_size=500, max_trades=3)
