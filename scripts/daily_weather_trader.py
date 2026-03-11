#!/usr/bin/env python3
"""
Daily Weather Trader - Automated daily run (V4 Model)
"""
import os
import sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

import json
from datetime import datetime
from gatherer.sources.openmeteo import OpenMeteoGatherer
from modeler.predictive_model_v4 import WeatherPredictorV4
from evaluator.trade_evaluator_v3 import TradeEvaluatorV3

# City coordinates database
CITY_COORDS = {
    'new york': (40.71, -74.01), 'nyc': (40.71, -74.01),
    'chicago': (41.88, -87.63), 'miami': (25.76, -80.19),
    'los angeles': (34.05, -118.24), 'la': (34.05, -118.24),
    'houston': (29.76, -95.37), 'dallas': (32.78, -96.80),
    'seattle': (47.61, -122.33), 'denver': (39.74, -104.99),
    'boston': (42.36, -71.06), 'atlanta': (33.75, -84.39),
    'phoenix': (33.45, -112.07), 'london': (51.51, -0.13),
    'seoul': (37.57, 126.98), 'tokyo': (35.68, 139.76),
    'sydney': (-33.87, 151.21), 'toronto': (43.65, -79.38),
}

# US cities ONLY - strictly enforced
US_CITIES = {
    'new york', 'nyc', 'chicago', 'miami', 'los angeles', 'la',
    'houston', 'dallas', 'seattle', 'denver', 'boston', 'atlanta', 'phoenix'
}

BLOCKED_CITIES = {'london', 'seoul', 'tokyo', 'sydney', 'toronto'}

def extract_city_coordinates(question: str):
    """Extract city coordinates from question - US cities ONLY"""
    q_lower = question.lower()
    for city, coords in CITY_COORDS.items():
        if city in q_lower:
            # Strictly enforce US cities only
            if city in US_CITIES:
                return coords
            elif city in BLOCKED_CITIES:
                return None
    return None

def run_daily_trading(target_date_str=None):
    """Run daily paper trading"""
    print("=" * 60)
    print("🌤️ Daily Weather Paper Trading")
    print(f"Time: {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    print("=" * 60)
    
    # Step 1: Always run scraper to get fresh market data - REQUIRED, no fallback to stale cache
    print("\n📡 Fetching fresh market data...")
    import subprocess
    scraper_path = os.path.join(os.path.dirname(__file__), '..', 'src', 'scraper', 'weather_scraper.py')
    
    scraper_success = False
    max_retries = 3
    last_error = None
    
    for attempt in range(max_retries):
        if attempt > 0:
            print(f"   🔄 Retry attempt {attempt + 1}/{max_retries}...")
            import time
            time.sleep(2 ** attempt)  # Exponential backoff
        
        try:
            result = subprocess.run(
                [sys.executable, scraper_path],
                capture_output=True,
                text=True,
                timeout=300
            )
            if result.returncode == 0:
                # Parse the last line to get count
                lines = result.stdout.strip().split('\n')
                for line in lines[-5:]:
                    if 'TOTAL:' in line or 'Saved' in line:
                        print(f"   {line.strip()}")
                print("   ✅ Fresh data loaded successfully")
                scraper_success = True
                break
            else:
                last_error = f"Scraper exit code {result.returncode}: {result.stderr[:200]}"
                print(f"   ⚠️ Scraper failed (attempt {attempt + 1}): {result.stderr[:100]}")
        except subprocess.TimeoutExpired:
            last_error = "Scraper timed out after 300 seconds"
            print(f"   ⚠️ Scraper timed out (attempt {attempt + 1})")
        except Exception as e:
            last_error = str(e)
            print(f"   ⚠️ Scraper error (attempt {attempt + 1}): {str(e)[:60]}")
    
    if not scraper_success:
        print(f"\n❌ CRITICAL: Failed to fetch fresh market data after {max_retries} attempts")
        print(f"   Last error: {last_error}")
        print("   🚫 Trading session ABORTED - refusing to use stale cached data")
        print("\n💡 To manually run: python src/scraper/weather_scraper.py")
        return
    
    # Step 2: Load markets and validate freshness
    try:
        filepath = 'data/markets/weather_full.json'
        with open(filepath) as f:
            markets = json.load(f)
        
        # Check file age
        file_mtime = os.path.getmtime(filepath)
        file_age_hours = (datetime.now().timestamp() - file_mtime) / 3600
        
        if file_age_hours > 2:
            print(f"❌ STALE DATA: Market file is {file_age_hours:.1f} hours old (max: 2 hours)")
            print("   🚫 Trading session ABORTED - data too old")
            print("   💡 Try running: python src/scraper/weather_scraper.py")
            return
        
        print(f"   📊 Loaded {len(markets)} markets (file age: {file_age_hours:.1f}h)")
        
    except FileNotFoundError:
        print("❌ No market data file found. Cannot continue.")
        print("   💡 Run: python src/scraper/weather_scraper.py")
        return
    except Exception as e:
        print(f"❌ Error loading markets: {e}")
        return
    
    # Use provided date or default to today
    if target_date_str:
        target_date = datetime.strptime(target_date_str, '%Y-%m-%d').date()
    else:
        target_date = datetime.now().date()
    
    print(f"📅 Target date: {target_date}")
    
    # Find target date's weather markets
    todays_markets = []
    skipped_non_us = 0
    for m in markets:
        q = m.get('question', '').lower()
        if 'temperature' not in q and 'snow' not in q:
            continue
        
        end = m.get('end_date', '')
        if not end:
            continue
        
        try:
            end_date = datetime.fromisoformat(end.replace('Z', '+00:00')).date()
            if end_date == target_date:
                prices = m.get('prices', {})
                yes_price = prices.get('Yes', {}).get('price', 0)
                if 0.05 < yes_price < 0.95:  # Reasonable prices
                    coords = extract_city_coordinates(m['question'])
                    if coords:
                        todays_markets.append({
                            'market': m,
                            'coords': coords,
                            'end_date': end_date,
                            'yes_price': yes_price
                        })
                    elif any(city in m['question'].lower() for city in BLOCKED_CITIES):
                        skipped_non_us += 1
        except:
            pass
    
    print(f"\n📊 Found {len(todays_markets)} US weather markets for {target_date}")
    if skipped_non_us > 0:
        print(f"🚫 Filtered {skipped_non_us} non-US city markets (enforcing US-only rule)")
    
    if not todays_markets:
        print("No actionable markets for this date.")
        return
    
    # Initialize components
    gatherer = OpenMeteoGatherer()
    predictor = WeatherPredictorV4()
    evaluator = TradeEvaluatorV3(bankroll=50000.0)
    
    # Analyze all viable markets, then trade top 3 by edge
    analyzed_results = []
    
    for item in todays_markets:
        m = item['market']
        lat, lon = item['coords']
        target = item['end_date'].strftime('%Y-%m-%d')
        
        print(f"\n📍 {m['question'][:50]}...")
        
        try:
            # Gather data
            climatology = gatherer.get_historical_for_date(lat, lon, item['end_date'].month, item['end_date'].day, years=20)
            forecast = gatherer.get_forecast(lat, lon, target)
            
            weather_data = {
                'climatology': climatology,
                'forecast': forecast
            }
            
            # Parse threshold
            import re
            threshold = {'value': 0, 'direction': 'above', 'question': m['question']}
            range_match = re.search(r'(\d+)[-–](\d+)', m['question'])
            if range_match:
                threshold['value'] = f"{range_match.group(1)}-{range_match.group(2)}"
                threshold['direction'] = 'between'
            else:
                num_match = re.search(r'(\d+)(?:\s*°|\s*degrees|\s*C|\s*F)?', m['question'])
                if num_match:
                    threshold['value'] = int(num_match.group(1))
                    if any(x in m['question'].lower() for x in ['below', 'under', 'or below']):
                        threshold['direction'] = 'below'
            
            # Predict
            market = {
                'market_id': m.get('condition_id', 'unknown'),
                'question': m['question'],
                'threshold': threshold,
                'target_date': target,
                'current_price_yes': item['yes_price'],
                'current_price_no': 1 - item['yes_price']
            }
            
            pred = predictor.predict(market, weather_data)
            
            if 'error' in pred:
                print(f"   ⚠️ {pred['error']}")
                continue
            
            model_prob = pred['prediction']['probability_yes']
            side = pred['recommendation']['side']
            
            # Calculate edge correctly based on side
            if side == 'YES':
                # Edge = Model YES prob - Market YES price
                edge = model_prob - item['yes_price']
            else:
                # Edge = Model NO prob - Market NO price
                model_no_prob = 1 - model_prob
                market_no_price = 1 - item['yes_price']
                edge = model_no_prob - market_no_price
            
            edge_pct = edge / (item['yes_price'] if side == 'YES' else (1 - item['yes_price']))
            
            print(f"   Market: {item['yes_price']:.1%} | Model: {model_prob:.1%} | Side: {side} | Edge: {edge_pct*100:+.1f}%")
            
            # Store result with correct edge for ranking
            result = evaluator.evaluate(pred)
            result['edge'] = edge_pct  # Store the CORRECT edge for this side
            result['side'] = side
            result['market_info'] = item
            analyzed_results.append(result)
            
            if result['decision'] == 'EXECUTE':
                print(f"   📊 EDGE: +{edge:.1f}% (candidate)")
            else:
                print(f"   ⏭️ {result['reason']}")
                
        except Exception as e:
            print(f"   ❌ Error: {str(e)[:40]}")
    
    # Sort by absolute edge descending, take top 3 with edge > min_threshold
    MIN_EDGE_THRESHOLD = 0.15  # 15% minimum edge (increased from 10% for better quality)
    
    # Filter trades that passed evaluation and have sufficient edge
    valid_trades = [r for r in analyzed_results 
                    if r['decision'] == 'EXECUTE' and abs(r['edge']) >= MIN_EDGE_THRESHOLD]
    
    # Sort by absolute edge (highest edge first regardless of side)
    valid_trades.sort(key=lambda x: abs(x['edge']), reverse=True)
    
    trades_to_execute = valid_trades[:3]
    trades_executed = []
    
    print(f"\n🏆 Top {len(trades_to_execute)} trades selected from {len(valid_trades)} candidates")
    
    for trade in trades_to_execute:
        # Override position size to fixed $500
        trade['recommendation']['size_usd'] = 500.0
        
        result = evaluator.execute_paper_trade(trade)
        
        # Recalculate shares for $500 position
        side = trade['recommendation']['side']
        market_price = trade['market_info']['yes_price'] if side == 'YES' else (1 - trade['market_info']['yes_price'])
        shares = int(500.0 / market_price) if market_price > 0 else 0
        
        # Clean result for JSON serialization
        clean_result = {
            'market_id': result['market_id'],
            'market_question': trade['market_info']['market']['question'],
            'recommendation': {
                'side': side,
                'size_usd': 500.0,
                'shares': shares,
                'is_maker': trade['recommendation'].get('is_maker', False),
                'confidence': trade['recommendation'].get('confidence', 'medium')
            },
            'expected_value': result.get('expected_value', {}),
            'confidence': result.get('confidence', 'medium'),
            'edge': trade['edge']
        }
        trades_executed.append(clean_result)
        m = trade['market_info']['market']
        print(f"   ✅ EXECUTED: {m['question'][:45]}...")
        print(f"      {side} $500 (edge: +{trade['edge']:.1f}%)")
    
    # Report
    print("\n" + "=" * 60)
    print("📊 Daily Summary")
    print("=" * 60)
    print(f"Markets analyzed: {len(todays_markets)}")
    print(f"Execution candidates: {len(valid_trades)}")
    print(f"Trades executed: {len(trades_executed)}")
    if skipped_non_us > 0:
        print(f"Non-US markets filtered: {skipped_non_us}")
    
    if trades_executed:
        total = sum(t['recommendation']['size_usd'] for t in trades_executed)
        print(f"Total exposure: ${total:,.0f}")
        print("\nExecuted:")
        for t in trades_executed:
            print(f"  • {t['market_id'][:20]}: {t['recommendation']['side']} ${t['recommendation']['size_usd']:,.0f}")
    
    # Build prediction log for tracking model accuracy over time
    predictions_log = []
    for item in analyzed_results:
        pred = item.get('prediction', {})
        comp = item.get('market_comparison', {})
        m = item.get('market_info', {}).get('market', {})
        
        predictions_log.append({
            'market_id': m.get('condition_id', 'unknown'),
            'question': m.get('question', '')[:100],
            'model_prob_yes': pred.get('probability_yes'),
            'market_price_yes': comp.get('market_price_yes'),
            'edge_percent': comp.get('edge_percent'),
            'forecast_weight': comp.get('forecast_weight', 0.90),
            'kelly_half': comp.get('kelly_half'),
            'side': item.get('recommendation', {}).get('side'),
            'executed': item.get('decision') == 'EXECUTE' and abs(comp.get('edge_percent', 0)) >= 0.15,
            'target_date': m.get('end_date'),
            'forecast_temp': pred.get('forecast_temp'),
            'data_source': pred.get('data_source', 'unknown')
        })
    
    # Save report with predictions log
    report = {
        'date': target_date.isoformat(),
        'time': datetime.now().isoformat(),
        'markets_analyzed': len(todays_markets),
        'execution_candidates': len(valid_trades),
        'trades_executed': len(trades_executed),
        'non_us_filtered': skipped_non_us,
        'trades': trades_executed,
        'predictions': predictions_log  # NEW: Track for accuracy analysis
    }
    
    report_file = f"data/positions/daily_reports/{target_date}.json"
    os.makedirs(os.path.dirname(report_file), exist_ok=True)
    with open(report_file, 'w') as f:
        json.dump(report, f, indent=2)
    
    print(f"\n💾 Report saved to {report_file}")

if __name__ == "__main__":
    import sys
    target_date = sys.argv[1] if len(sys.argv) > 1 else None
    run_daily_trading(target_date)
