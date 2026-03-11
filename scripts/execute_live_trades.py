#!/usr/bin/env python3
"""
Execute 4 Live Paper Trades - Future Markets
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

CITY_COORDS = {
    'chicago': (41.88, -87.63), 'miami': (25.76, -80.19),
    'dallas': (32.78, -96.80), 'houston': (29.76, -95.37),
    'new york': (40.71, -74.01), 'nyc': (40.71, -74.01),
}

def extract_city_data(question: str):
    q_lower = question.lower()
    for city, coords in CITY_COORDS.items():
        if city in q_lower:
            return city.title(), coords
    return None, None

def run_live_trades(max_trades=4):
    """Execute live paper trades on best future markets"""
    print("=" * 70)
    print("🎯 LIVE PAPER TRADING - V4 Model")
    print(f"Time: {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    print("=" * 70)
    
    # Load markets
    try:
        with open('data/markets/weather_full.json') as f:
            markets = json.load(f)
    except:
        print("❌ No market data found.")
        return
    
    today = datetime.now().date()
    gatherer = OpenMeteoGatherer()
    predictor = WeatherPredictorV4()
    evaluator = TradeEvaluatorV3(bankroll=50000.0)
    
    # Collect all future markets with edges
    opportunities = []
    
    for days in range(1, 5):  # Next 4 days
        target_date = today + timedelta(days=days)
        
        for m in markets:
            q = m.get('question', '').lower()
            if 'temperature' not in q:
                continue
            
            end = m.get('end_date', '')
            if not end:
                continue
            
            try:
                end_date = datetime.fromisoformat(end.replace('Z', '+00:00')).date()
                if end_date != target_date:
                    continue
                
                city, coords = extract_city_data(m['question'])
                if not coords:
                    continue
                
                prices = m.get('prices', {})
                yes_price = prices.get('Yes', {}).get('price', 0)
                if not (0.05 < yes_price < 0.95):
                    continue
                
                lat, lon = coords
                target = end_date.strftime('%Y-%m-%d')
                
                # Get weather data
                climatology = gatherer.get_historical_for_date(lat, lon, end_date.month, end_date.day, years=20)
                forecast = gatherer.get_forecast(lat, lon, target)
                
                if not climatology or not forecast:
                    continue
                
                # Parse threshold
                range_match = re.search(r'(\d+)[-–](\d+)', m['question'])
                if range_match:
                    threshold = {'value': f"{range_match.group(1)}-{range_match.group(2)}", 'direction': 'between'}
                else:
                    num_match = re.search(r'(\d+)', m['question'])
                    if not num_match:
                        continue
                    val = int(num_match.group(1))
                    if any(x in q for x in ['below', 'under', 'or below']):
                        threshold = {'value': val, 'direction': 'below'}
                    else:
                        threshold = {'value': val, 'direction': 'above'}
                
                market = {
                    'market_id': m.get('condition_id', 'unknown'),
                    'question': m['question'],
                    'threshold': threshold,
                    'target_date': target,
                    'current_price_yes': yes_price,
                    'current_price_no': 1 - yes_price
                }
                
                weather_data = {'climatology': climatology, 'forecast': forecast}
                pred = predictor.predict(market, weather_data)
                
                if 'error' in pred:
                    continue
                
                result = evaluator.evaluate(pred)
                edge = pred['market_comparison']['edge_percent']
                
                opportunities.append({
                    'market': market,
                    'city': city,
                    'date': target,
                    'prediction': pred,
                    'result': result,
                    'edge': edge,
                    'abs_edge': abs(edge)
                })
                
            except Exception as e:
                continue
    
    # Sort by absolute edge and take top trades
    opportunities.sort(key=lambda x: x['abs_edge'], reverse=True)
    
    print(f"\n📊 Analyzed {len(opportunities)} future markets")
    print(f"🎯 Executing top {max_trades} trades by edge magnitude\n")
    
    # Execute trades
    trades_executed = []
    for item in opportunities[:max_trades]:
        m = item['market']
        p = item['prediction']
        r = item['result']
        
        if r['decision'] != 'EXECUTE':
            continue
        
        # Execute paper trade
        trade = evaluator.execute_paper_trade(r)
        trades_executed.append(trade)
        
        print(f"✅ TRADE {len(trades_executed)}: {item['city']} - {item['date']}")
        print(f"   {m['question'][:50]}...")
        print(f"   Side: {r['recommendation']['side']} | Size: ${r['recommendation']['size_usd']:.0f}")
        print(f"   Market: {m['current_price_yes']:.1%} | Model: {p['prediction']['probability_yes']:.1%}")
        print(f"   Edge: {item['edge']:+.1%}")
        print()
    
    # Summary
    print("=" * 70)
    print("📊 EXECUTION SUMMARY")
    print("=" * 70)
    print(f"Markets analyzed: {len(opportunities)}")
    print(f"Trades executed: {len(trades_executed)}")
    
    if trades_executed:
        total = sum(t['recommendation']['size_usd'] for t in trades_executed)
        print(f"Total exposure: ${total:,.0f}")
        print("\nExecuted trades:")
        for i, t in enumerate(trades_executed, 1):
            print(f"  {i}. {t['market_id'][:20]}: {t['recommendation']['side']} ${t['recommendation']['size_usd']:,.0f}")
    
    # Save report
    report = {
        'date': today.isoformat(),
        'time': datetime.now().isoformat(),
        'type': 'live_paper_trades',
        'markets_analyzed': len(opportunities),
        'trades_executed': len(trades_executed),
        'trades': trades_executed
    }
    
    report_file = f"data/positions/live_trades/{today}_manual.json"
    os.makedirs(os.path.dirname(report_file), exist_ok=True)
    with open(report_file, 'w') as f:
        json.dump(report, f, indent=2)
    
    print(f"\n💾 Report saved to {report_file}")

if __name__ == "__main__":
    run_live_trades(max_trades=4)
