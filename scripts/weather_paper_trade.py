#!/usr/bin/env python3
"""
Weather Paper Trade - One-command weather market paper trading
Uses scraped weather market data
"""
import os
import sys
import json
from datetime import datetime

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

from gatherer.sources.openmeteo import OpenMeteoGatherer
from modeler.predictive_model_v3 import WeatherPredictorV3
from evaluator.trade_evaluator_v3 import TradeEvaluatorV3

def load_weather_markets(filepath='data/markets/weather_full.json'):
    """Load scraped weather markets"""
    if not os.path.exists(filepath):
        print(f"❌ No weather markets file found at {filepath}")
        print("   Run: python src/scraper/weather_scraper.py")
        return []
    
    with open(filepath, 'r') as f:
        return json.load(f)

def run_pipeline(
    bankroll: float = 100000.0,
    min_edge: float = 0.07,
    max_trades: int = 1
):
    """Run paper trading pipeline on weather markets"""
    
    print("=" * 60)
    print("🏁 WEATHER MARKET PAPER TRADING SYSTEM")
    print("=" * 60)
    print(f"Bankroll: ${bankroll:,.0f}")
    print(f"Min Edge: {min_edge:.0%}")
    print("=" * 60)
    print()
    
    # === PHASE 1: LOAD MARKETS ===
    print("📚 Loading weather markets from scraped data...")
    markets = load_weather_markets()
    
    if not markets:
        return []
    
    # Filter to markets with condition IDs and prices
    valid_markets = []
    for m in markets:
        if m.get('condition_id') and m.get('prices'):
            prices = m.get('prices', {})
            if 'Yes' in prices or 'No' in prices:
                valid_markets.append(m)
    
    print(f"✅ Found {len(valid_markets)} markets with price data")
    print()
    
    # === PHASE 2: FILTER TO TEMPERATURE/SNOW MARKETS ===
    temp_markets = []
    for m in valid_markets:
        q = m.get('question', '').lower()
        if 'temperature' in q or 'snow' in q or 'inch' in q:
            # Extract location
            location = extract_location(q)
            threshold = extract_threshold(q)
            target_date = extract_date(q)
            
            if location.get('lat') and threshold:
                m['location'] = location
                m['threshold'] = threshold
                m['target_date'] = target_date
                temp_markets.append(m)
    
    print(f"🌡️  Temperature/snow markets: {len(temp_markets)}")
    print()
    
    if not temp_markets:
        print("❌ No analyzable temperature markets found")
        return []
    
    # === PHASE 3: GATHER WEATHER DATA ===
    print("🌤️ PHASE 3: Gathering Open-Meteo data...")
    gatherer = OpenMeteoGatherer()
    
    markets_with_data = []
    for market in temp_markets[:max_trades * 3]:
        try:
            location = market['location']
            threshold = market['threshold']
            target_date = market['target_date']
            
            # Use end_date from market data if available
            if not target_date and market.get('end_date'):
                end = market['end_date']
                if 'T' in end:
                    target_date = end.split('T')[0]
            
            if not target_date:
                print(f"   ⚠️ No specific date for: {market['question'][:40]}...")
                continue
            
            print(f"   📍 {location['city']}: {threshold['direction']} {threshold['value']}{threshold['unit']} on {target_date}")
            
            # Parse date
            year, month, day = target_date.split('-')
            month, day = int(month), int(day)
            
            # Get climatology (historical data for same month/day across years)
            climatology = gatherer.get_historical_for_date(
                location['lat'], location['lon'], month, day, years=20
            )
            
            if climatology.get('years_available', 0) < 10:
                print(f"      ⚠️ Insufficient historical data ({climatology.get('years_available', 0)} years)")
                continue
            
            # Calculate threshold probability
            clim_prob = gatherer.calculate_threshold_probability(
                climatology, threshold['value'], threshold['direction']
            )
            
            # Get forecast
            forecast = gatherer.get_forecast(location['lat'], location['lon'], target_date)
            
            weather_data = {
                'climatology': {**climatology, 'baseline_probability_combined': clim_prob.get('baseline_probability_empirical', 0.3)},
                'forecast': forecast
            }
            
            markets_with_data.append({
                'market': market,
                'weather_data': weather_data
            })
            
            print(f"      ✅ {climatology.get('years_available', 0)} years historical")
            
        except Exception as e:
            print(f"      ❌ Error: {e}")
            continue
    
    print(f"✅ Gathered weather data for {len(markets_with_data)} markets\n")
    
    if not markets_with_data:
        print("❌ No markets with valid weather data")
        return []
    
    # === PHASE 4: MODEL ===
    print("🤖 PHASE 4: Running predictive models (V3)...")
    predictor = WeatherPredictorV3()
    
    predictions = []
    for item in markets_with_data:
        try:
            # Format for predictor
            market = item['market']
            pred_input = {
                'market_id': market['condition_id'],
                'question': market['question'],
                'location': market['location'],
                'threshold': market['threshold'],
                'target_date': market['target_date'],
                'current_price_yes': market['prices'].get('Yes', {}).get('price', 0.5),
                'current_price_no': market['prices'].get('No', {}).get('price', 0.5),
            }
            
            pred = predictor.predict(pred_input, item['weather_data'])
            predictions.append(pred)
            
            edge_pct = pred['market_comparison']['edge_percent'] * 100
            print(f"   📊 {market['question'][:50]}...")
            print(f"      Market: {pred['market_comparison']['market_price_yes']:.3f} | Model: {pred['prediction']['probability_yes']:.3f} | Edge: {edge_pct:.1f}%")
            
        except Exception as e:
            print(f"      ❌ Error modeling: {e}")
            continue
    
    print(f"✅ Generated {len(predictions)} predictions\n")
    
    if not predictions:
        print("❌ No valid predictions")
        return []
    
    # === PHASE 5: EVALUATE & TRADE ===
    print("💰 PHASE 5: Evaluating trades (V3 fee-aware)...")
    evaluator = TradeEvaluatorV3(bankroll=bankroll, use_maker_orders=False)
    
    trades_executed = []
    trades_evaluated = 0
    
    for pred in predictions:
        try:
            pred['market_location'] = {'city': 'Weather Market'}
            result = evaluator.evaluate(pred)
            trades_evaluated += 1
            
            if result['decision'] == 'EXECUTE':
                result = evaluator.execute_paper_trade(result)
                trades_executed.append(result)
                
                rec = result['recommendation']
                print(f"\n   ✅ PAPER TRADE EXECUTED:")
                print(f"      {result['question'][:55]}...")
                print(f"      Side: {rec['side']} | Size: ${rec['size_usd']:,.0f} | Shares: {rec['shares']}")
                print(f"      Edge: {result['risk_analysis']['edge_pct']*100:.1f}% | Kelly: {result['risk_analysis']['kelly_fractional']*100:.2f}%")
                print(f"      ID: {result['paper_trade']['paper_trade_id']}")
                
                if len(trades_executed) >= max_trades:
                    print(f"\n   🎯 Max trades ({max_trades}) reached")
                    break
            else:
                print(f"   ⏭️  {result['reason']}")
                
        except Exception as e:
            print(f"   ❌ Error: {e}")
            continue
    
    # === SUMMARY ===
    print()
    print("=" * 60)
    print("📋 PAPER TRADING SUMMARY")
    print("=" * 60)
    print(f"Markets loaded: {len(valid_markets)}")
    print(f"Temperature markets: {len(temp_markets)}")
    print(f"Markets analyzed: {len(markets_with_data)}")
    print(f"Predictions generated: {len(predictions)}")
    print(f"Trades evaluated: {trades_evaluated}")
    print(f"Paper trades executed: {len(trades_executed)}")
    
    if trades_executed:
        total_exposure = sum(t['recommendation']['size_usd'] for t in trades_executed)
        print(f"Total exposure: ${total_exposure:,.0f}")
        print(f"Portfolio utilization: {total_exposure/bankroll*100:.1f}%")
        print()
        print("📈 Trades:")
        for t in trades_executed:
            print(f"   • {t['paper_trade']['paper_trade_id']}: {t['recommendation']['side']} ${t['recommendation']['size_usd']:,.0f}")
    
    print("=" * 60)
    
    # Save summary
    summary = {
        'timestamp': datetime.now().isoformat(),
        'bankroll': bankroll,
        'markets_loaded': len(valid_markets),
        'markets_analyzed': len(markets_with_data),
        'predictions_generated': len(predictions),
        'trades_evaluated': trades_evaluated,
        'trades_executed': len(trades_executed),
        'trades': trades_executed
    }
    
    os.makedirs('data/trades', exist_ok=True)
    with open('data/trades/latest_run.json', 'w') as f:
        json.dump(summary, f, indent=2, default=str)
    
    return trades_executed


def extract_location(question):
    """Extract location from question"""
    q = question.lower()
    cities = {
        'nyc': ('New York City', 40.71, -74.01, 'US'),
        'new york': ('New York City', 40.71, -74.01, 'US'),
        'chicago': ('Chicago', 41.88, -87.63, 'US'),
        'miami': ('Miami', 25.76, -80.19, 'US'),
        'atlanta': ('Atlanta', 33.75, -84.39, 'US'),
        'dallas': ('Dallas', 32.78, -96.80, 'US'),
        'seattle': ('Seattle', 47.61, -122.33, 'US'),
        'toronto': ('Toronto', 43.65, -79.38, 'CA'),
        'london': ('London', 51.51, -0.13, 'UK'),
        'paris': ('Paris', 48.86, 2.35, 'FR'),
        'buenos aires': ('Buenos Aires', -34.60, -58.38, 'AR'),
        'sao paulo': ('Sao Paulo', -23.55, -46.63, 'BR'),
        'seoul': ('Seoul', 37.57, 126.98, 'KR'),
        'tokyo': ('Tokyo', 35.68, 139.69, 'JP'),
        'wellington': ('Wellington', -41.29, 174.78, 'NZ'),
    }
    
    for key, (name, lat, lon, country) in cities.items():
        if key in q:
            return {'city': name, 'lat': lat, 'lon': lon, 'country': country}
    
    return {'city': 'Unknown', 'lat': None, 'lon': None, 'country': 'Unknown'}


def extract_threshold(question):
    """Extract threshold from question"""
    import re
    q = question.lower()
    
    # Snow inches
    inch_match = re.search(r'(\d+)[\s-]*\d*\s*inch', q)
    if inch_match:
        return {'value': int(inch_match.group(1)), 'unit': 'inches', 'direction': 'above'}
    
    # Temperature
    temp_match = re.search(r'(\d+).*degree', q)
    if temp_match:
        direction = 'above' if 'highest' in q or 'above' in q else 'below'
        return {'value': int(temp_match.group(1)), 'unit': 'F', 'direction': direction}
    
    return None


def extract_date(question):
    """Extract date from question"""
    import re
    from datetime import datetime
    
    q = question.lower()
    months = {
        'january': 1, 'february': 2, 'march': 3, 'april': 4,
        'may': 5, 'june': 6, 'july': 7, 'august': 8,
        'september': 9, 'october': 10, 'november': 11, 'december': 12
    }
    
    # Try to find "on February 23" pattern
    pattern = r'on\s+(january|february|march|april|may|june|july|august|september|october|november|december)\s+(\d{1,2})'
    match = re.search(pattern, q)
    if match:
        month_name = match.group(1)
        day = int(match.group(2))
        month_num = months[month_name]
        year = datetime.now().year
        return f"{year}-{month_num:02d}-{day:02d}"
    
    # Try "february 23" without "on"
    for month_name, month_num in months.items():
        if month_name in q:
            # Look for day number after month
            idx = q.find(month_name)
            after_month = q[idx + len(month_name):idx + len(month_name) + 10]
            day_match = re.search(r'\s*(\d{1,2})\b', after_month)
            if day_match:
                day = int(day_match.group(1))
                year = datetime.now().year
                return f"{year}-{month_num:02d}-{day:02d}"
    
    return None


def main():
    import argparse
    parser = argparse.ArgumentParser(description='Weather Paper Trading')
    parser.add_argument('--bankroll', type=float, default=100000.0)
    parser.add_argument('--min-edge', type=float, default=0.07)
    parser.add_argument('--max-trades', type=int, default=1)
    args = parser.parse_args()
    
    trades = run_pipeline(
        bankroll=args.bankroll,
        min_edge=args.min_edge,
        max_trades=args.max_trades
    )
    
    return 0 if trades else 1


if __name__ == "__main__":
    main()