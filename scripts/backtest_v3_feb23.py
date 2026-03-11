#!/usr/bin/env python3
"""
Backtest V3 model against Feb 23 actual weather
"""
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

from modeler.predictive_model_v3 import WeatherPredictorV3
import json

# Actual weather on Feb 23, 2026:
ACTUAL_WEATHER = {
    'chicago': {'temp_max': 26.1, 'temp_mean': 23, 'uncertainty': 4},
    'nyc': {'snowfall': 5.1, 'snowfall_uncertainty': 2.0}
}

CLIMATOLOGY = {
    'chicago': {'mean_temp': 35, 'std_dev': 8},
    'nyc': {'mean_snow': 3.0, 'std_snow': 3.0}
}

# Markets that were traded on Feb 23
MARKETS = [
    {
        'market_id': 'chicago_30_31',
        'question': 'Chicago 30-31°F',
        'threshold': {'value': '30-31', 'direction': 'between', 'question': 'Will temp be 30-31°F?'},
        'city': 'chicago',
        'actual_temp': 26.1,
    },
    {
        'market_id': 'chicago_32_33',
        'question': 'Chicago 32-33°F',
        'threshold': {'value': '32-33', 'direction': 'between', 'question': 'Will temp be 32-33°F?'},
        'city': 'chicago',
        'actual_temp': 26.1,
    },
    {
        'market_id': 'chicago_34_35',
        'question': 'Chicago 34-35°F',
        'threshold': {'value': '34-35', 'direction': 'between', 'question': 'Will temp be 34-35°F?'},
        'city': 'chicago',
        'actual_temp': 26.1,
    },
    {
        'market_id': 'chicago_36_37',
        'question': 'Chicago 36-37°F',
        'threshold': {'value': '36-37', 'direction': 'between', 'question': 'Will temp be 36-37°F?'},
        'city': 'chicago',
        'actual_temp': 26.1,
    },
    {
        'market_id': 'chicago_38_39',
        'question': 'Chicago 38-39°F',
        'threshold': {'value': '38-39', 'direction': 'between', 'question': 'Will temp be 38-39°F?'},
        'city': 'chicago',
        'actual_temp': 26.1,
    },
    {
        'market_id': 'nyc_snow_8_10',
        'question': 'NYC 8-10 inches snow',
        'threshold': {'value': '8-10', 'direction': 'between', 'question': 'Will snowfall be 8-10 inches?'},
        'city': 'nyc',
        'metric': 'snow',
        'actual_snow': 5.1,
    },
    {
        'market_id': 'nyc_snow_10_12',
        'question': 'NYC 10-12 inches snow',
        'threshold': {'value': '10-12', 'direction': 'between', 'question': 'Will snowfall be 10-12 inches?'},
        'city': 'nyc',
        'metric': 'snow',
        'actual_snow': 5.1,
    }
]

def backtest_v3():
    predictor = WeatherPredictorV3()
    
    print("🧪 Backtesting V3 Model vs Feb 23 Actual Weather")
    print("=" * 70)
    print(f"\nActual Weather:")
    print(f"  Chicago High: {ACTUAL_WEATHER['chicago']['temp_max']}°F")
    print(f"  NYC Snow: {ACTUAL_WEATHER['nyc']['snowfall']}")
    print()
    
    results = []
    correct_predictions = 0
    
    for market in MARKETS:
        # Build weather data input
        if market.get('metric') == 'snow':
            weather_data = {
                'forecast': ACTUAL_WEATHER['nyc'],
                'climatology': CLIMATOLOGY['nyc']
            }
            actual_in_range = market['threshold']['low'] <= market['actual_snow'] <= market['threshold']['high'] if 'low' in market['threshold'] else False
        else:
            weather_data = {
                'forecast': ACTUAL_WEATHER['chicago'],
                'climatology': CLIMATOLOGY['chicago']
            }
            # Parse threshold to get range
            low, high, _, metric_type = predictor._parse_threshold(market['threshold'])
            actual_in_range = low <= market['actual_temp'] <= high
        
        # Run prediction
        pred = predictor.predict(market, weather_data)
        
        model_prob_yes = pred['prediction']['probability_yes']
        model_says_yes = model_prob_yes > 0.5
        
        # Check correctness
        v3_correct = (model_says_yes and actual_in_range) or (not model_says_yes and not actual_in_range)
        if v3_correct:
            correct_predictions += 1
        
        # Compare to what v1 did (bet YES on everything)
        v1_bet = 'YES'
        v1_correct = (v1_bet == 'YES' and actual_in_range) or (v1_bet == 'NO' and not actual_in_range)
        
        results.append({
            'market': market['question'],
            'actual_in_range': actual_in_range,
            'v1_bet': v1_bet,
            'v1_correct': v1_correct,
            'v3_prob_yes': model_prob_yes,
            'v3_bet': 'YES' if model_says_yes else 'NO',
            'v3_correct': v3_correct
        })
        
        print(f"📊 {market['question']}")
        print(f"   Actual in range: {actual_in_range}")
        print(f"   V1 bet: {v1_bet} → {'✅' if v1_correct else '❌'}")
        print(f"   V3 bet: {'YES' if model_says_yes else 'NO'} ({model_prob_yes:.1%}) → {'✅' if v3_correct else '❌'}")
        print()
    
    # Summary
    v1_wins = sum(1 for r in results if r['v1_correct'])
    v3_wins = sum(1 for r in results if r['v3_correct'])
    
    print("=" * 70)
    print("📊 Backtest Summary")
    print("=" * 70)
    print(f"Total Markets: {len(results)}")
    print()
    print(f"V1 Model (climatology-weighted):")
    print(f"  Correct predictions: {v1_wins}/{len(results)} ({v1_wins/len(results)*100:.1f}%)")
    print(f"  Strategy: Bet YES on everything → Lost money")
    print()
    print(f"V3 Model (forecast-weighted, bounded):")
    print(f"  Correct predictions: {v3_wins}/{len(results)} ({v3_wins/len(results)*100:.1f}%)")
    if v3_wins > v1_wins:
        print(f"  ✅ Improvement: +{v3_wins - v1_wins} correct predictions")
    else:
        print(f"  ⚠️  No improvement (needs more work)")
    print()
    
    # Save results
    summary = {
        'date': '2026-02-23',
        'actual_weather': ACTUAL_WEATHER,
        'results': results,
        'v1_accuracy': v1_wins / len(results),
        'v3_accuracy': v3_wins / len(results)
    }
    
    summary_file = 'data/positions/v3_backtest_feb23.json'
    os.makedirs(os.path.dirname(summary_file), exist_ok=True)
    with open(summary_file, 'w') as f:
        json.dump(summary, f, indent=2)
    
    print(f"💾 Saved to {summary_file}")
    
    return v3_wins, v1_wins, len(results)

if __name__ == "__main__":
    backtest_v3()
