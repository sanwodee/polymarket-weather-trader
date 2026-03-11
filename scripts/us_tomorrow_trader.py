#!/usr/bin/env python3
"""
US Cities Weather Trader - Tomorrow's Best Opportunities
$500 paper trades, top 3 by edge
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
    range_match = re.search(r'(\d+)[-–]\s*(\d+)', question)
    if range_match:
        low = int(range_match.group(1))
        high = int(range_match.group(2))
        return {'value': f"{low}-{high}", 'direction': 'between', 'low': low, 'high': high}
    
    num_match = re.search(r'(\d+)(?:\s*°|\s*degrees)', question)
    if num_match:
        value = int(num_match.group(1))
        q_lower = question.lower()
        if any(x in q_lower for x in ['below', 'under', 'or below', 'less than', '≤']):
            return {'value': value, 'direction': 'below'}
        elif any(x in q_lower for x in ['above', 'over', 'or above', 'more than', '≥']):
            return {'value': value, 'direction': 'above'}
        elif 'between' in q_lower or 'and' in q_lower:
            nums = re.findall(r'\d+', q_lower)
            if len(nums) >= 2:
                return {'value': f"{nums[0]}-{nums[1]}", 'direction': 'between', 'low': int(nums[0]), 'high': int(nums[1])}
    return None

def run_us_tomorrow_trades(max_trades=3, trade_size=500):
    """Run paper trading on US cities for tomorrow only"""
    print("=" * 70)
    print("🇺🇸 US CITIES WEATHER TRADER - TOMORROW'S OPPORTUNITIES")
    print(f"Time: {datetime.now().strftime('%Y-%m-%d %H:%M %Z')}")
    print(f"Trade Size: ${trade_size} | Max Trades: {max_trades}")
    print("=" * 70)
    
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
    
    print(f"\n📅 Today: {today}")
    print(f"📅 Target: Tomorrow ({tomorrow})")
    
    # Find US city weather markets for TOMORROW only
    us_markets = []
    for m in markets:
        q = m.get('question', '')
        q_lower = q.lower()
        
        if 'temperature' not in q_lower:
            continue
        
        city_name, coords = extract_us_city(q)
        if not city_name:
            continue
        
        end = m.get('end_date', '')
        if not end:
            continue
        
        try:
            end_date = datetime.fromisoformat(end.replace('Z', '+00:00')).date()
            # ONLY tomorrow's markets
            if end_date != tomorrow:
                continue
            
            prices = m.get('prices', {})
            yes_price = prices.get('Yes', {}).get('price', 0)
            no_price = prices.get('No', {}).get('price', 0)
            
            # Viable price range
            if yes_price < 0.02 or yes_price > 0.98:
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
                'threshold': threshold,
                'question': q
            })
        except:
            pass
    
    print(f"\n📊 Found {len(us_markets)} US city markets closing TOMORROW")
    
    if not us_markets:
        print("\n❌ No US city markets for tomorrow")
        return
    
    # Show candidate markets
    print(f"\n📈 Candidate Markets (tomorrow {tomorrow}):")
    for m in us_markets:
        t = m['threshold']
        if t['direction'] == 'between':
            thresh_str = f"{t['low']}-{t['high']}°F"
        elif t['direction'] == 'below':
            thresh_str = f"≤{t['value']}°F"
        else:
            thresh_str = f"≥{t['value']}°F"
        
        city_display = m['city'].title()
        print(f"  • {city_display}: {thresh_str}")
        print(f"    Yes: {m['yes_price']:.2%} | No: {m['no_price']:.2%} | Vol: ${m['volume']:,.0f}")
    
    print()
    
    # Initialize V4 components
    gatherer = OpenMeteoGatherer()
    predictor = WeatherPredictorV4()
    evaluator = TradeEvaluatorV3(bankroll=10000.0)
    
    # Analyze all markets
    opportunities = []
    
    print("🌤️ Analyzing all US markets with live weather data...")
    
    for item in us_markets:
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
                continue
            
            model_prob = pred['prediction']['probability_yes']
            edge = pred['market_comparison']['edge_percent']
            net_edge = pred['market_comparison'].get('net_edge_percent', edge * 0.92)  # After 4% fees
            
            # Evaluate trade
            result = evaluator.evaluate(pred)
            
            if result['decision'] == 'EXECUTE':
                opportunities.append({
                    'item': item,
                    'pred': pred,
                    'result': result,
                    'model_prob': model_prob,
                    'edge': edge,
                    'net_edge': net_edge,
                    'thresh_str': thresh_str
                })
                
        except Exception as e:
            pass
    
    print(f"\n✅ Found {len(opportunities)} viable trading opportunities")
    
    if not opportunities:
        print("\n❌ No trades meet criteria after analysis")
        return
    
    # Sort by absolute net edge (highest edge first)
    opportunities.sort(key=lambda x: abs(x['net_edge']), reverse=True)
    
    # Execute top N trades at $500 each
    trades_executed = []
    
    print(f"\n💰 EXECUTING TOP {min(max_trades, len(opportunities))} TRADES AT ${trade_size} EACH:")
    print("=" * 70)
    
    for i, opp in enumerate(opportunities[:max_trades], 1):
        item = opp['item']
        result = opp['result']
        city = item['city'].title()
        
        # Override trade size to $500
        result['recommendation']['size_usd'] = trade_size
        result['recommendation']['shares'] = trade_size  # $1 per share approx
        
        # Execute paper trade
        trade_result = evaluator.execute_paper_trade(result)
        trades_executed.append(trade_result)
        
        rec = trade_result['recommendation']
        risk = trade_result['risk_analysis']
        
        print(f"\n{i}. {city} - {opp['thresh_str']}")
        print(f"   Market: Yes {item['yes_price']:.2%} | Model: {opp['model_prob']:.1%}")
        print(f"   🎯 TRADE: {rec['side']} ${rec['size_usd']:.0f}")
        print(f"   Net Edge: {risk['net_edge_pct']:.1%} | Expected Profit: ${risk['net_ev']:.0f}")
        print(f"   Trade ID: {trade_result['paper_trade']['paper_trade_id']}")
        print(f"   Market ID: {item['market'].get('condition_id', 'unknown')[:20]}...")
    
    # Summary
    print("\n" + "=" * 70)
    print("📊 EXECUTION SUMMARY")
    print("=" * 70)
    print(f"US Markets Found: {len(us_markets)}")
    print(f"Viable Opportunities: {len(opportunities)}")
    print(f"Trades Executed: {len(trades_executed)}")
    
    if trades_executed:
        total = sum(t['recommendation']['size_usd'] for t in trades_executed)
        total_ev = sum(t['risk_analysis']['net_ev'] for t in trades_executed)
        print(f"\nTotal Capital Deployed: ${total:.0f}")
        print(f"Total Expected Net Profit: ${total_ev:.0f}")
        
        print(f"\n📋 Active Positions:")
        for i, t in enumerate(trades_executed, 1):
            rec = t['recommendation']
            print(f"  {i}. {rec['side']} {t['market_id'][:30]}... - ${rec['size_usd']:.0f}")
        
        print(f"\n⏰ Settles: {tomorrow} (tomorrow)")
        print(f"\n💡 To check results tomorrow:")
        print(f"   python src/evaluator/outcome_tracker.py")
    
    # Save report
    report = {
        'date': today.isoformat(),
        'target_date': tomorrow.isoformat(),
        'us_markets_found': len(us_markets),
        'opportunities': len(opportunities),
        'trades_executed': len(trades_executed),
        'total_deployed': sum(t['recommendation']['size_usd'] for t in trades_executed),
        'total_expected_ev': sum(t['risk_analysis']['net_ev'] for t in trades_executed),
        'trades': trades_executed,
        'all_opportunities': [
            {
                'city': o['item']['city'],
                'threshold': o['thresh_str'],
                'yes_price': o['item']['yes_price'],
                'model_prob': o['model_prob'],
                'net_edge': o['net_edge'],
                'market_id': o['item']['market'].get('condition_id', 'unknown')
            }
            for o in opportunities
        ]
    }
    
    report_file = f'data/positions/us_tomorrow_report_{tomorrow}.json'
    os.makedirs(os.path.dirname(report_file), exist_ok=True)
    with open(report_file, 'w') as f:
        json.dump(report, f, indent=2)
    print(f"\n💾 Report saved to {report_file}")
    
    return trades_executed


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument('--size', type=int, default=500, help='Trade size in USD')
    parser.add_argument('--max-trades', type=int, default=3, help='Max trades to execute')
    args = parser.parse_args()
    
    run_us_tomorrow_trades(max_trades=args.max_trades, trade_size=args.size)
