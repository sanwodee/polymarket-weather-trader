#!/usr/bin/env python3
"""
Outcome Tracker - Mark paper trades as resolved and track PnL
"""
import json
import os
from datetime import datetime
from typing import Dict, List, Optional


def load_trades(filepath: str = 'data/positions/paper_trades_v3.jsonl') -> List[Dict]:
    """Load all paper trades"""
    if not os.path.exists(filepath):
        return []
    
    trades = []
    with open(filepath, 'r') as f:
        for line in f:
            trade = json.loads(line.strip())
            trades.append(trade)
    return trades


def get_unresolved_trades(trades: List[Dict]) -> List[Dict]:
    """Get trades that haven't been resolved yet"""
    return [t for t in trades if not t.get('resolved', False)]


def mark_trade_resolved(trade_id: str, outcome: bool, filepath: str = 'data/positions/paper_trades_v3.jsonl') -> Dict:
    """
    Mark a trade as resolved
    
    Args:
        trade_id: The paper_trade_id string
        outcome: True if YES outcome, False if NO
    
    Returns:
        Updated trade dict with PnL calculated
    """
    trades = load_trades(filepath)
    updated_trade = None
    
    for i, trade in enumerate(trades):
        if trade.get('paper_trade_id') == trade_id:
            side = trade.get('side', 'YES')
            size = trade.get('size_usd', 0)
            fees = trade.get('fee_cost', 0)
            
            # Calculate PnL
            if side == 'YES':
                if outcome:  # YES outcome happened
                    pnl = size - fees  # Won: get stake back minus fees
                else:  # NO outcome happened
                    pnl = -size - fees  # Lost: lost stake plus fees
            else:  # NO side
                if not outcome:  # NO outcome happened
                    pnl = size - fees
                else:  # YES outcome happened
                    pnl = -size - fees
            
            trades[i]['resolved'] = True
            trades[i]['actual_outcome'] = outcome
            trades[i]['pnl'] = round(pnl, 2)
            trades[i]['resolved_at'] = datetime.now().isoformat()
            updated_trade = trades[i]
            break
    
    if not updated_trade:
        return {'error': f'Trade {trade_id} not found'}
    
    # Rewrite file
    with open(filepath, 'w') as f:
        for trade in trades:
            f.write(json.dumps(trade) + '\n')
    
    return updated_trade


def calculate_performance(filepath: str = 'data/positions/paper_trades_v3.jsonl') -> Dict:
    """Calculate overall performance stats"""
    trades = load_trades(filepath)
    
    resolved = [t for t in trades if t.get('resolved', False)]
    unresolved = [t for t in trades if not t.get('resolved', False)]
    
    if not resolved:
        return {
            'total_trades': len(trades),
            'resolved_trades': 0,
            'win_rate': 0,
            'total_pnl': 0,
            'message': 'No resolved trades yet'
        }
    
    wins = [t for t in resolved if t.get('pnl', 0) > 0]
    losses = [t for t in resolved if t.get('pnl', 0) <= 0]
    
    total_pnl = sum(t.get('pnl', 0) for t in resolved)
    win_rate = len(wins) / len(resolved) if resolved else 0
    
    return {
        'total_trades': len(trades),
        'resolved_trades': len(resolved),
        'unresolved_trades': len(unresolved),
        'win_rate': win_rate,
        'wins': len(wins),
        'losses': len(losses),
        'total_pnl': round(total_pnl, 2),
        'avg_pnl_per_trade': round(total_pnl / len(resolved), 2) if resolved else 0,
        'roi_percent': round((total_pnl / sum(t.get('size_usd', 0) for t in resolved)) * 100, 2) if resolved else 0
    }


def main():
    """CLI for outcome tracking"""
    import sys
    
    if len(sys.argv) < 2:
        print("Usage:")
        print("  python outcome_tracker.py list           # List all unresolved trades")
        print("  python outcome_tracker.py resolve <trade_id> <yes|no>   # Mark outcome")
        print("  python outcome_tracker.py performance    # Show performance stats")
        return
    
    command = sys.argv[1]
    
    if command == 'list':
        trades = load_trades()
        unresolved = get_unresolved_trades(trades)
        
        if not unresolved:
            print("No unresolved trades")
            return
        
        print(f"\n📋 Unresolved Trades ({len(unresolved)}):")
        print("=" * 60)
        for t in unresolved[-10:]:  # Show last 10
            print(f"\nID: {t['paper_trade_id']}")
            print(f"  Market: {t['market_id'][:30]}...")
            print(f"  Side: {t['side']}")
            print(f"  Size: ${t['size_usd']:,.0f}")
            print(f"  Expected Profit: ${t.get('expected_net_profit', 0):,.0f}")
    
    elif command == 'resolve' and len(sys.argv) >= 4:
        trade_id = sys.argv[2]
        outcome = sys.argv[3].lower() == 'yes'
        
        result = mark_trade_resolved(trade_id, outcome)
        
        if 'error' in result:
            print(f"❌ {result['error']}")
        else:
            print(f"✅ Trade resolved!")
            print(f"   Outcome: {'YES' if outcome else 'NO'}")
            print(f"   PnL: ${result['pnl']:,.2f}")
    
    elif command == 'performance':
        stats = calculate_performance()
        
        print("\n📊 Performance Summary")
        print("=" * 60)
        print(f"Total trades: {stats['total_trades']}")
        print(f"Resolved: {stats['resolved_trades']}")
        print(f"Unresolved: {stats.get('unresolved_trades', 0)}")
        
        if stats['resolved_trades'] > 0:
            print(f"\nWin rate: {stats['win_rate']:.1%}")
            print(f"Wins: {stats['wins']} | Losses: {stats['losses']}")
            print(f"Total PnL: ${stats['total_pnl']:,.2f}")
            print(f"ROI: {stats['roi_percent']:.1f}%")
            print(f"Avg per trade: ${stats['avg_pnl_per_trade']:,.2f}")


if __name__ == "__main__":
    main()
