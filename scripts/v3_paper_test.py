#!/usr/bin/env python3
"""
V3 Paper Test - 5 small trades for validation
"""
import os
import sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

from evaluator.trade_evaluator_v3 import TradeEvaluatorV3
import json
from datetime import datetime

print("=" * 60)
print("🧪 V3 Paper Trading Test - $100/trade")
print("=" * 60)

# Use V3 evaluator directly with small positions
evaluator = TradeEvaluatorV3(bankroll=500.0, use_maker_orders=False)

# 5 test predictions from current run
test_predictions = [
    {
        'market_id': 'test_1',
        'question': 'Test trade 1',
        'prediction': {'probability_yes': 0.15, 'confidence': 'medium'},
        'market_comparison': {
            'market_price_yes': 0.05,
            'divergence': 0.10,
            'edge_percent': 2.0,  # Should reject (needs 10%)
            'kelly_fraction': 0.5
        },
        'recommendation': {'side': 'YES', 'confidence': 'medium'}
    },
    {
        'market_id': 'test_2',
        'question': 'Test trade 2',
        'prediction': {'probability_yes': 0.65, 'confidence': 'high'},
        'market_comparison': {
            'market_price_yes': 0.40,
            'divergence': 0.25,
            'edge_percent': 0.625,  # Should trade
            'kelly_fraction': 0.3
        },
        'recommendation': {'side': 'YES', 'confidence': 'high'}
    },
    {
        'market_id': 'test_3',
        'question': 'Test trade 3',
        'prediction': {'probability_yes': 0.75, 'confidence': 'high'},
        'market_comparison': {
            'market_price_yes': 0.45,
            'divergence': 0.30,
            'edge_percent': 0.67,
            'kelly_fraction': 0.4
        },
        'recommendation': {'side': 'YES', 'confidence': 'high'}
    },
    {
        'market_id': 'test_4',
        'question': 'Test trade 4',
        'prediction': {'probability_yes': 0.25, 'confidence': 'medium'},
        'market_comparison': {
            'market_price_yes': 0.60,
            'divergence': -0.35,
            'edge_percent': -0.58,
            'kelly_fraction': 0
        },
        'recommendation': {'side': 'NO', 'confidence': 'medium'}
    },
    {
        'market_id': 'test_5',
        'question': 'Test trade 5',
        'prediction': {'probability_yes': 0.85, 'confidence': 'high'},
        'market_comparison': {
            'market_price_yes': 0.55,
            'divergence': 0.30,
            'edge_percent': 0.545,
            'kelly_fraction': 0.45
        },
        'recommendation': {'side': 'YES', 'confidence': 'high'}
    }
]

trades_executed = []
trades_rejected = []

for i, pred in enumerate(test_predictions, 1):
    print(f"\n{i}. {pred['question']}")
    print(f"   Market: {pred['market_comparison']['market_price_yes']:.0%} | Model: {pred['prediction']['probability_yes']:.0%}")
    
    result = evaluator.evaluate(pred)
    
    print(f"   Edge: {pred['market_comparison']['edge_percent']:.0%}")
    print(f"   Decision: {result['decision']}")
    
    if result['decision'] == 'EXECUTE':
        result = evaluator.execute_paper_trade(result)
        trades_executed.append(result)
        print(f"   ✅ EXECUTED: {result['recommendation']['side']} ${result['recommendation']['size_usd']:.0f}")
        print(f"   Net EV: {result['risk_analysis']['net_ev_pct']:.1%}")
        print(f"   Trade ID: {result['paper_trade']['paper_trade_id']}")
    else:
        trades_rejected.append(result)
        print(f"   ⏭️ REJECTED: {result['reason']}")

print("\n" + "=" * 60)
print("📊 Summary")
print("=" * 60)
print(f"Total tested: {len(test_predictions)}")
print(f"Executed: {len(trades_executed)}")
print(f"Rejected: {len(trades_rejected)}")

if trades_executed:
    print(f"\nExecuted Trades:")
    for t in trades_executed:
        print(f"  • {t['market_id']}: {t['recommendation']['side']} ${t['recommendation']['size_usd']:.0f}")
        print(f"    ID: {t['paper_trade']['paper_trade_id']}")
    
    total = sum(t['recommendation']['size_usd'] for t in trades_executed)
    print(f"\nTotal Exposure: ${total:.0f}")

print("\n💡 To resolve trades tomorrow:")
print("   python src/evaluator/outcome_tracker.py resolve <trade_id> yes|no")

# Save executed trades to summary
summary = {
    'test_date': datetime.now().isoformat(),
    'total_tested': len(test_predictions),
    'executed': len(trades_executed),
    'rejected': len(trades_rejected),
    'executed_trades': [{
        'id': t['paper_trade']['paper_trade_id'],
        'market': t['market_id'],
        'side': t['recommendation']['side'],
        'size': t['recommendation']['size_usd'],
        'net_ev': t['risk_analysis']['net_ev_pct']
    } for t in trades_executed]
}

with open('data/positions/v3_test_trades.json', 'w') as f:
    json.dump(summary, f, indent=2)

print("\n💾 Saved to data/positions/v3_test_trades.json")
