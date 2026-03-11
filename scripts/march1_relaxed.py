#!/usr/bin/env python3
"""
US March 1st trades - Relaxed threshold variant
Captures borderline opportunities
"""
import os
import sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

import json
import re
from datetime import datetime, timedelta
from gatherer.sources.openmeteo import OpenMeteoGatherer
from modeler.predictive_model_v4 import WeatherPredictorV4

# Patch evaluator temporarily for this run
class RelaxedEvaluator:
    MIN_EDGE_PCT = 0.05  # 5% instead of 10%
    TAKER_FEE_BPS = 200
    KELLY_FRACTION = 0.15
    
    def __init__(self, bankroll=10000):
        self.bankroll = bankroll
    
    def calculate_net_edge(self, gross_edge_pct, position_size):
        fee_rate = self.TAKER_FEE_BPS / 10000
        total_fees = position_size * fee_rate * 2  # Entry + exit
        net_ev_pct = gross_edge_pct - (total_fees / position_size if position_size > 0 else 0)
        return net_ev_pct
    
    def evaluate(self, prediction, item):
        model_prob = prediction['prediction']['probability_yes']
        market_price_yes = prediction['market_comparison']['market_price_yes']
        gross_edge = prediction['market_comparison']['edge_percent']
        side = prediction['recommendation']['side']
        
        # Position sizing
        gross_position = 500  # Fixed $500
        
        # Calculate net edge after 4% fees
        fee_cost = gross_position * 0.04
        win_prob = model_prob if side == 'YES' else (1 - model_prob)
        
        if side == 'YES':
            shares = gross_position / market_price_yes
            potential_payout = shares * 1.0
            gross_profit = potential_payout - gross_position
        else:
            market_price_no = 1 - market_price_yes
            shares = gross_position / market_price_no
            potential_payout = shares * 1.0
            gross_profit = potential_payout - gross_position
        
        expected_gross = gross_profit * win_prob - gross_position * (1 - win_prob)
        net_ev = expected_gross - fee_cost
        net_ev_pct = net_ev / gross_position if gross_position > 0 else 0
        
        # Relaxed criteria: gross edge > 5% and net EV positive
        if gross_edge >= self.MIN_EDGE_PCT and net_ev > 0:
            return {
                'decision': 'EXECUTE',
                'side': side,
                'size_usd': 500,
                'shares': int(shares),
                'gross_edge': gross_edge,
                'net_ev': net_ev,
                'net_ev_pct': net_ev_pct,
                'fee_cost': fee_cost
            }
        return {'decision': 'PASS', 'reason': f'Edge {gross_edge:.1%} or net EV ${net_ev:.0f}'}

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

def extract_city(question):
    q_lower = question.lower()
    for city, coords in US_CITIES.items():
        if city in q_lower:
            return city, coords
    return None, None

def parse_thresh(question):
    range_match = re.search(r'(\d+)[-–]\s*(\d+)', question)
    if range_match:
        return {'low': int(range_match.group(1)), 'high': int(range_match.group(2)), 'dir': 'between'}
    num_match = re.search(r'(\d+)', question)
    if num_match:
        val = int(num_match.group(1))
        if any(x in question.lower() for x in ['below', 'under']):
            return {'value': val, 'dir': 'below'}
        return {'value': val, 'dir': 'above'}
    return None

def execute_march1_relaxed():
    print("="*70)
    print("🇺🇸 MARCH 1 TRADES - RELAXED THRESHOLD (5% edge)")
    print("="*70)
    
    with open('data/markets/weather_full.json') as f:
        markets = json.load(f)
    
    target_date = datetime.now().date() + timedelta(days=2)
    print(f"\n📅 Target: {target_date} (Sunday March 1)")
    
    # Find US markets
    us_markets = []
    for m in markets:
        q = m.get('question', '')
        if 'temperature' not in q.lower():
            continue
        city, coords = extract_city(q)
        if not city:
            continue
        try:
            end_date = datetime.fromisoformat(m['end_date'].replace('Z', '+00:00')).date()
            if end_date != target_date:
                continue
            prices = m.get('prices', {})
            yes_price = prices.get('Yes', {}).get('price', 0)
            if 0.01 < yes_price < 0.99:
                thresh = parse_thresh(q)
                if thresh:
                    us_markets.append({
                        'market': m, 'city': city, 'coords': coords,
                        'yes_price': yes_price,
                        'no_price': prices.get('No', {}).get('price', 0),
                        'threshold': thresh,
                        'question': q
                    })
        except:
            pass
    
    print(f"📊 US markets: {len(us_markets)}")
    
    # Analyze
    gatherer = OpenMeteoGatherer()
    predictor = WeatherPredictorV4()
    evaluator = RelaxedEvaluator()
    
    opportunities = []
    
    for item in us_markets:
        m = item['market']
        city = item['city']
        lat, lon = item['coords']
        target = target_date.strftime('%Y-%m-%d')
        
        t = item['threshold']
        if t.get('dir') == 'between':
            thresh_str = f"{t['low']}-{t['high']}°F"
        elif t.get('dir') == 'below':
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
                'threshold': t,
                'target_date': target,
                'current_price_yes': item['yes_price'],
                'current_price_no': item['no_price']
            }
            
            pred = predictor.predict(market, weather_data)
            if 'error' in pred:
                continue
            
            result = evaluator.evaluate(pred, item)
            
            if result['decision'] == 'EXECUTE':
                opportunities.append({
                    'item': item,
                    'pred': pred,
                    'result': result,
                    'thresh_str': thresh_str,
                    'forecast': forecast,
                    'model_prob': pred['prediction']['probability_yes'],
                    'gross_edge': result['gross_edge']
                })
        except:
            pass
    
    print(f"✅ Qualifying opportunities (5%+ edge, +EV): {len(opportunities)}")
    
    if not opportunities:
        print("❌ No qualifying trades")
        return
    
    # Sort by gross edge descending
    opportunities.sort(key=lambda x: x['gross_edge'], reverse=True)
    
    # Show all qualifying
    print("\n📋 ALL QUALIFYING OPPORTUNITIES:")
    print("-"*70)
    for i, opp in enumerate(opportunities, 1):
        item = opp['item']
        res = opp['result']
        print(f"{i}. {item['city'].title()} - {opp['thresh_str']}")
        print(f"   Forecast: {opp['forecast'].get('temp_max', 'N/A')}°F")
        print(f"   Market Yes: {item['yes_price']:.1%} | Model: {opp['model_prob']:.1%}")
        print(f"   Gross Edge: {res['gross_edge']:.1f}% | Net EV: ${res['net_ev']:.0f} ({res['net_ev_pct']:.1f}%)")
        print(f"   Side: {res['side']}")
        print()
    
    # Execute top 3
    max_trades = min(3, len(opportunities))
    print(f"💰 EXECUTING TOP {max_trades} TRADES AT $500 EACH:")
    print("="*70)
    
    trades = []
    for i, opp in enumerate(opportunities[:max_trades], 1):
        item = opp['item']
        res = opp['result']
        trade_id = f"paper_{datetime.now().strftime('%Y%m%d%H%M%S')}_{i}"
        
        trade = {
            'market_id': item['market'].get('condition_id', 'unknown'),
            'paper_trade_id': trade_id,
            'city': item['city'].title(),
            'threshold': opp['thresh_str'],
            'side': res['side'],
            'size_usd': 500,
            'gross_edge': res['gross_edge'],
            'net_ev': res['net_ev'],
            'status': 'PAPER_FILLED',
            'timestamp': datetime.now().isoformat()
        }
        trades.append(trade)
        
        print(f"\n{i}. {trade['city']} - {opp['thresh_str']}")
        print(f"   Forecast: {opp['forecast'].get('temp_max', 'N/A')}°F high")
        print(f"   🎯 {res['side']} ${res['size_usd']}")
        print(f"   Gross Edge: {res['gross_edge']:.1f}% | Net EV: ${res['net_ev']:.0f}")
        print(f"   Trade ID: {trade_id}")
    
    # Save
    report = {
        'date': datetime.now().isoformat(),
        'target_date': target_date.isoformat(),
        'markets_analyzed': len(us_markets),
        'opportunities': len(opportunities),
        'trades_executed': len(trades),
        'total_deployed': sum(t['size_usd'] for t in trades),
        'total_net_ev': sum(t['net_ev'] for t in trades),
        'trades': trades
    }
    
    report_file = 'data/positions/march1_relaxed_trades.json'
    os.makedirs(os.path.dirname(report_file), exist_ok=True)
    with open(report_file, 'w') as f:
        json.dump(report, f, indent=2)
    
    print(f"\n💾 Report: {report_file}")
    print(f"⏰ Settles: Sunday March 1")
    
    return trades

if __name__ == "__main__":
    execute_march1_relaxed()
