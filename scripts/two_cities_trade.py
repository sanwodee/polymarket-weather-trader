#!/usr/bin/env python3
"""
2 US Cities Paper Trade - One market from Chicago, one from Miami
"""
import os
import sys
import json
from datetime import datetime

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

from gatherer.sources.openmeteo import OpenMeteoGatherer
from modeler.predictive_model_v3 import WeatherPredictorV3
from evaluator.trade_evaluator_v3 import TradeEvaluatorV3

def run_two_cities(bankroll=100000.0):
    print("=" * 60)
    print("🇺🇸 2 US CITIES PAPER TRADING")
    print("=" * 60)
    print(f"Bankroll: ${bankroll:,.0f}")
    print("=" * 60)
    print()
    
    # Load markets
    with open('data/markets/weather_full.json', 'r') as f:
        markets = json.load(f)
    
    # Find one Chicago and one Miami market
    chicago_market = None
    miami_market = None
    
    for m in markets:
        q = m.get('question', '').lower()
        prices = m.get('prices', {})
        
        if not prices or not m.get('end_date'):
            continue
            
        if 'highest temperature' in q:
            # Get a reasonable market (not $0 or $1)
            yes_price = prices.get('Yes', {}).get('price', 0)
            if 0.05 < yes_price < 0.95:  # Some uncertainty
                if 'chicago' in q and not chicago_market:
                    chicago_market = m
                    chicago_market['city'] = 'Chicago'
                    chicago_market['lat'] = 41.88
                    chicago_market['lon'] = -87.63
                elif 'miami' in q and not miami_market:
                    miami_market = m
                    miami_market['city'] = 'Miami'
                    miami_market['lat'] = 25.76
                    miami_market['lon'] = -80.19
    
    selected_markets = []
    if chicago_market:
        selected_markets.append(chicago_market)
    if miami_market:
        selected_markets.append(miami_market)
    
    print(f"✅ Selected {len(selected_markets)} markets:")
    for m in selected_markets:
        prices = m.get('prices', {})
        print(f"  • {m['city']}: {m.get('question')[:50]}...")
        print(f"    Yes: ${prices.get('Yes', {}).get('price', 'N/A')}")
        print(f"    Date: {m.get('end_date', 'N/A')[:10]}")
    print()
    
    # Gather weather data
    print("🌤️ Gathering Open-Meteo data...")
    gatherer = OpenMeteoGatherer()
    
    markets_with_data = []
    for market in selected_markets:
        try:
            city = market['city']
            date = market['end_date'].split('T')[0]
            
            print(f"   📍 {city} on {date}")
            
            # Parse date
            year, month, day = date.split('-')
            month, day = int(month), int(day)
            
            # Get climatology
            climatology = gatherer.get_historical_for_date(
                market['lat'], market['lon'], month, day, years=20
            )
            
            if climatology.get('years_available', 0) < 10:
                print(f"      ⚠️ Insufficient data")
                continue
            
            # Extract threshold from question
            import re
            q = market.get('question', '').lower()
            match = re.search(r'(\d+)[°\s]*f', q)
            if match:
                threshold_val = int(match.group(1))
                direction = 'below' if 'below' in q or 'or below' in q else 'above'
                
                clim_prob = gatherer.calculate_threshold_probability(
                    climatology, threshold_val, direction
                )
                
                forecast = gatherer.get_forecast(market['lat'], market['lon'], date)
                
                weather_data = {
                    'climatology': {
                        **climatology,
                        'baseline_probability_combined': clim_prob.get('baseline_probability_empirical', 0.5)
                    },
                    'forecast': forecast
                }
                
                markets_with_data.append({
                    'market': market,
                    'weather_data': weather_data,
                    'threshold': {'value': threshold_val, 'direction': direction, 'unit': 'F'}
                })
                
                print(f"      ✅ {climatology.get('years_available')} years data")
                print(f"      Historical mean: {climatology.get('mean_temp'):.1f}°F")
        except Exception as e:
            print(f"      ❌ Error: {e}")
    
    print(f"\n✅ Gathered data for {len(markets_with_data)} markets\n")
    
    if len(markets_with_data) < 2:
        print("❌ Need 2 markets with data")
        return []
    
    # Run predictions
    print("🤖 Running models...")
    predictor = WeatherPredictorV3()
    
    predictions = []
    for item in markets_with_data[:2]:
        try:
            market = item['market']
            prices = market.get('prices', {})
            
            pred_input = {
                'market_id': market.get('condition_id', 'unknown'),
                'question': market['question'],
                'location': {'city': market['city'], 'lat': market['lat'], 'lon': market['lon']},
                'threshold': item['threshold'],
                'target_date': market['end_date'].split('T')[0],
                'current_price_yes': prices.get('Yes', {}).get('price', 0.5),
                'current_price_no': prices.get('No', {}).get('price', 0.5),
            }
            
            pred = predictor.predict(pred_input, item['weather_data'])
            predictions.append(pred)
            
            # Debug output
            print(f"      DEBUG: forecast={item['weather_data'].get('forecast')}")
            print(f"      DEBUG: climatology mean={item['weather_data'].get('climatology', {}).get('mean_temp')}")
            
            edge_pct = pred['market_comparison']['edge_percent'] * 100
            breakdown = pred['prediction'].get('model_breakdown', {})
            fcst_prob = breakdown.get('forecast', {}).get('probability')
            clim_prob = breakdown.get('climatology', {}).get('probability')
            fcst_mean = breakdown.get('forecast', {}).get('mean')
            
            print(f"\n   📊 {market['city']}: {market['question'][:45]}...")
            print(f"      Forecast mean: {fcst_mean}, Forecast P: {fcst_prob}")
            print(f"      Climatology P: {clim_prob}")
            print(f"      Market P(Yes): {pred['market_comparison']['market_price_yes']:.3f}")
            print(f"      Model P(Yes): {pred['prediction']['probability_yes']:.3f}")
            print(f"      Edge: {edge_pct:.1f}%")
        except Exception as e:
            print(f"      ❌ Error: {e}")
    
    # Evaluate trades
    print("\n💰 Evaluating trades (fee-aware)...")
    evaluator = TradeEvaluatorV3(bankroll=bankroll, use_maker_orders=False)
    print("   Accounting for 2% taker fee on both entry and exit")
    
    trades_executed = []
    for pred in predictions:
        try:
            pred['market_location'] = {'city': pred.get('location', {}).get('city', 'Unknown')}
            result = evaluator.evaluate(pred)
            
            if result['decision'] == 'EXECUTE':
                result = evaluator.execute_paper_trade(result)
                trades_executed.append(result)
                
                rec = result['recommendation']
                city = pred.get('location', {}).get('city', 'Unknown')
                edge_pct = result['risk_analysis'].get('edge_pct', result['risk_analysis'].get('gross_edge_pct', 0)) * 100
                print(f"\n   ✅ {city} PAPER TRADE:")
                print(f"      {rec['side']} ${rec['size_usd']:,.0f} | Edge: {edge_pct:.1f}%")
                print(f"      ID: {result['paper_trade']['paper_trade_id']}")
            else:
                print(f"   ⏭️  {result['reason']}")
        except Exception as e:
            print(f"   ❌ Error: {e}")
    
    # Summary
    print()
    print("=" * 60)
    print("📋 2 CITIES SUMMARY")
    print("=" * 60)
    print(f"Markets selected: {len(selected_markets)}")
    print(f"Markets analyzed: {len(markets_with_data)}")
    print(f"Paper trades: {len(trades_executed)}")
    
    if trades_executed:
        total = sum(t['recommendation']['size_usd'] for t in trades_executed)
        print(f"Total exposure: ${total:,.0f}")
        for t in trades_executed:
            city = t.get('question', '').split('in')[1].split('be')[0].strip() if 'in' in t.get('question', '') else 'Unknown'
            print(f"  • {city}: {t['recommendation']['side']} ${t['recommendation']['size_usd']:,.0f}")
    
    print("=" * 60)
    return trades_executed

if __name__ == "__main__":
    trades = run_two_cities(bankroll=100000.0)
