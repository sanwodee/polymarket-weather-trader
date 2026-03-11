#!/usr/bin/env python3
"""
Paper Trade Script - One-command weather market paper trading
Ties together: Scanner → Gatherer → Modeler → Evaluator
"""
import os
import sys
import json
from datetime import datetime

# Add src to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

from scanner.market_scanner import MarketScanner
from gatherer.sources.openmeteo import OpenMeteoGatherer
from modeler.predictive_model import WeatherPredictor
from evaluator.trade_evaluator_v2 import TradeEvaluatorV2

def run_pipeline(
    bankroll: float = 100000.0,
    min_score: float = 50.0,
    min_edge: float = 0.07,
    max_trades: int = 1
):
    """
    Run full paper trading pipeline
    
    1. Scan for weather markets
    2. Gather Open-Meteo data
    3. Run prediction model
    4. Evaluate edge and sizing
    5. Execute paper trades
    """
    
    print("=" * 60)
    print("🏁 WEATHER MARKET PAPER TRADING SYSTEM")
    print("=" * 60)
    print(f"Bankroll: ${bankroll:,.0f}")
    print(f"Min Market Score: {min_score}")
    print(f"Min Edge: {min_edge:.0%}")
    print("=" * 60)
    print()
    
    # === PHASE 1: SCAN ===
    print("🔍 PHASE 1: Scanning for weather markets...")
    scanner = MarketScanner()
    markets = scanner.scan(min_score=min_score)
    
    if not markets:
        print("❌ No weather markets found. Exiting.")
        return []
    
    # Filter to temperature markets we can analyze
    temp_markets = [
        m for m in markets 
        if m.get('threshold') and m['location'].get('lat') and m['location'].get('lon')
    ]
    
    if not temp_markets:
        print(f"❌ No temperature markets with location data found.")
        print(f"   Found {len(markets)} weather markets but need location coordinates.")
        return []
    
    print(f"✅ Found {len(temp_markets)} temperature markets to analyze\n")
    
    # === PHASE 2: GATHER ===
    print("🌤️ PHASE 2: Gathering weather data (Open-Meteo)...")
    gatherer = OpenMeteoGatherer()
    
    markets_with_data = []
    for market in temp_markets[:max_trades * 3]:  # Get extra for filtering
        try:
            location = market['location']
            threshold = market['threshold']
            target_date = market['target_date']
            
            print(f"   📍 {location['city']}: {threshold['direction']} {threshold['value']}°{threshold['unit']} on {target_date}")
            
            # Parse target date for historical
            if target_date:
                year, month, day = target_date.split('-')
                month, day = int(month), int(day)
            else:
                print(f"      ⚠️ No target date, skipping")
                continue
            
            # Get climatology (30 years)
            climatology = gatherer.get_historical_for_date(
                location['lat'], location['lon'], month, day, years=30
            )
            
            if climatology.get('years_available', 0) < 10:
                print(f"      ⚠️ Insufficient historical data ({climatology.get('years_available', 0)} years)")
                continue
            
            # Calculate threshold probability from climatology
            clim_prob = gatherer.calculate_threshold_probability(
                climatology, threshold['value'], threshold['direction']
            )
            
            # Get forecast if future date
            forecast = gatherer.get_forecast(location['lat'], location['lon'], target_date)
            
            weather_data = {
                'climatology': {
                    **climatology,
                    **climatology.get('baseline_probability_combined', 
                                     {'baseline_probability_combined': clim_prob.get('baseline_probability_empirical', 0.3)})
                },
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
        print("❌ No markets with valid weather data. Exiting.")
        return []
    
    # === PHASE 3: MODEL ===
    print("🤖 PHASE 3: Running predictive models...")
    predictor = WeatherPredictor()
    
    predictions = []
    for item in markets_with_data:
        try:
            pred = predictor.predict(item['market'], item['weather_data'])
            predictions.append(pred)
            
            mkt = item['market']
            edge_pct = pred['market_comparison']['edge_percent'] * 100
            print(f"   📊 {mkt['question'][:50]}...")
            print(f"      Market: {pred['market_comparison']['market_price_yes']:.2f} | Model: {pred['prediction']['probability_yes']:.2f} | Edge: {edge_pct:.1f}%")
            
        except Exception as e:
            print(f"      ❌ Error modeling: {e}")
            continue
    
    print(f"✅ Generated {len(predictions)} predictions\n")
    
    if not predictions:
        print("❌ No valid predictions. Exiting.")
        return []
    
    # === PHASE 4: EVALUATE ===
    print("💰 PHASE 4: Evaluating trades...")
    evaluator = TradeEvaluatorV2(bankroll=bankroll, use_maker_orders=False)
    
    trades_executed = []
    trades_evaluated = 0
    
    for pred in predictions:
        try:
            # Add market location to prediction for correlation checks
            pred['market_location'] = {
                'city': pred.get('location', {}).get('city', 'Unknown'),
                'target_date': pred.get('target_date')
            }
            
            result = evaluator.evaluate(pred)
            trades_evaluated += 1
            
            if result['decision'] == 'EXECUTE':
                # Execute paper trade
                result = evaluator.execute_paper_trade(result)
                trades_executed.append(result)
                
                rec = result['recommendation']
                print(f"   ✅ PAPER TRADE EXECUTED:")
                print(f"      {result['question'][:55]}...")
                print(f"      Side: {rec['side']} | Size: ${rec['size_usd']:,.0f} | Shares: {rec['shares']}")
                print(f"      Edge: {result['risk_analysis']['edge_pct']*100:.1f}% | Kelly: {result['risk_analysis']['kelly_fractional']*100:.2f}%")
                print(f"      Paper Trade ID: {result['paper_trade']['paper_trade_id']}")
                
                if len(trades_executed) >= max_trades:
                    print(f"\n   🎯 Max trades ({max_trades}) reached. Stopping.")
                    break
            else:
                print(f"   ⏭️  Skipped: {result['reason']}")
                
        except Exception as e:
            print(f"   ❌ Error evaluating: {e}")
            continue
    
    # === SUMMARY ===
    print()
    print("=" * 60)
    print("📋 PAPER TRADING SUMMARY")
    print("=" * 60)
    print(f"Markets scanned: {len(markets)}")
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
        'markets_scanned': len(markets),
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


def main():
    """CLI entry point"""
    import argparse
    
    parser = argparse.ArgumentParser(description='Weather Market Paper Trading')
    parser.add_argument('--bankroll', type=float, default=100000.0, help='Trading bankroll (default: 100000)')
    parser.add_argument('--min-score', type=float, default=50.0, help='Minimum market score (default: 50)')
    parser.add_argument('--min-edge', type=float, default=0.07, help='Minimum edge for trade (default: 0.07)')
    parser.add_argument('--max-trades', type=int, default=1, help='Max trades per run (default: 1)')
    
    args = parser.parse_args()
    
    trades = run_pipeline(
        bankroll=args.bankroll,
        min_score=args.min_score,
        min_edge=args.min_edge,
        max_trades=args.max_trades
    )
    
    return 0 if trades else 1


if __name__ == "__main__":
    main()
