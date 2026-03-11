#!/usr/bin/env python3
"""
Outcome Tracker - Tracks actual results of paper trades

Usage:
    python scripts/outcome_tracker.py --list          # Show unresolved trades
    python scripts/outcome_tracker.py --resolve trade_id --outcome yes/no
    python scripts/outcome_tracker.py --report       # Show PnL summary
"""
import json
import os
import sys
import argparse
from datetime import datetime
from typing import Dict, List, Optional

def load_trades(v3=True):
    """Load paper trades"""
    log_file = 'data/positions/paper_trades_v3.jsonl' if v3 else 'data/positions/paper_trades.jsonl'
    if not os.path.exists(log_file):
        return []
    
    trades = []
    with open(log_file, 'r') as f:
        for line in f:
            try:
                trade = json.loads(line)
                trades.append(trade)
            except:
                continue
    return trades

def calculate_pnl(trade: Dict, outcome: bool) -> float:
    """Calculate PnL for a resolved trade"""
    side = trade.get('side', 'YES')
    size = trade.get('size_usd', 0)
    fees = trade.get('fee_cost', 0)
    
    if side == 'YES':
        if outcome:  # YES happened
            return size - fees  # Won: get back stake minus fees
        else:
            return -size - fees  # Lost: lost stake plus fees
    else:  # NO side
        if not outcome:  # NO happened (YES didn't)
            return size - fees
        else:
            return -size - fees

def mark_resolved(trade_id: str, outcome: bool, v3=True):
    """Mark a trade as resolved with actual outcome"""
    log_file = 'data/positions/paper_trades_v3.jsonl' if v3 else 'data/positions/paper_trades.jsonl'
    
    if not os.path.exists(log_file):
        print(f"❌ No trades file found: {log_file}")
        return
    
    trades = []
    found = False
    
    with open(log_file, 'r') as f:
        for line in f:
            trade = json.loads(line)
            if trade.get('paper_trade_id') == trade_id:
                pnl = calculate_pnl(trade, outcome)
                trade['resolved'] = True
                trade['actual_outcome'] = outcome
                trade['pnl'] = round(pnl, 2)
                trade['resolved_at'] = datetime.now().isoformat()
                found = True
                print(f"✅ Resolved {trade_id}: Outcome={'YES' if outcome else 'NO'}, PnL=${pnl:,.2f}")
            trades.append(trade)
    
    if not found:
        print(f"❌ Trade {trade_id} not found")
        return
    
    # Rewrite file
    with open(log_file, 'w') as f:
        for trade in trades:
            f.write(json.dumps(trade) + '\n')

def list_unresolved(v3=True):
    """Show unresolved trades"""
    trades = load_trades(v3)
    unresolved = [t for t in trades if not t.get('resolved', False)]
    
    if not unresolved:
        print("✅ No unresolved trades")
        return
    
    print(f"\n⏳ {len(unresolved)} Unresolved Trades:\n")
    print("-" * 80)
    for t in unresolved:
        trade_id = t.get('paper_trade_id', 'unknown')
        date = t.get('timestamp', '').split('T')[0] if 'T' in t.get('timestamp', '') else t.get('timestamp', 'unknown')[:10]
        side = t.get('side', 'YES')
        size = t.get('size_usd', 0)
        expected = t.get('expected_net_profit', 0)
        print(f"ID: {trade_id}")
        print(f"  Date: {date} | Side: {side} | Size: ${size:,.0f}")
        print(f"  Expected Profit: ${expected:,.2f}")
        print(f"-" * 80)

def show_report(v3=True):
    """Show PnL summary"""
    trades = load_trades(v3)
    
    resolved = [t for t in trades if t.get('resolved', False)]
    unresolved = [t for t in trades if not t.get('resolved', False)]
    
    total_trades = len(trades)
    total_resolved = len(resolved)
    total_unresolved = len(unresolved)
    
    print("\n📊 TRADE REPORT\n")
    print("=" * 60)
    print(f"Total Trades: {total_trades}")
    print(f"Resolved: {total_resolved}")
    print(f"Unresolved: {total_unresolved}")
    print()
    
    if resolved:
        total_pnl = sum(t.get('pnl', 0) for t in resolved)
        winning_trades = [t for t in resolved if t.get('pnl', 0) > 0]
        losing_trades = [t for t in resolved if t.get('pnl', 0) <= 0]
        
        win_rate = len(winning_trades) / len(resolved) * 100 if resolved else 0
        
        print(f"Total PnL: ${total_pnl:,.2f}")
        print(f"Win Rate: {win_rate:.1f}% ({len(winning_trades)}/{len(resolved)})")
        print(f"Avg Win: ${sum(t.get('pnl',0) for t in winning_trades)/len(winning_trades):,.2f}" if winning_trades else "Avg Win: N/A")
        print(f"Avg Loss: ${sum(t.get('pnl',0) for t in losing_trades)/len(losing_trades):,.2f}" if losing_trades else "Avg Loss: N/A")
        print()
        
        print("Resolved Trades:")
        print("-" * 60)
        for t in resolved[-10:]:  # Last 10
            trade_id = t.get('paper_trade_id', 'unknown')
            side = t.get('side', 'YES')
            outcome = 'YES' if t.get('actual_outcome') else 'NO'
            pnl = t.get('pnl', 0)
            symbol = "✅" if pnl > 0 else "❌"
            print(f"{symbol} {trade_id} | {side} | Outcome: {outcome} | PnL: ${pnl:,.2f}")
    
    print("=" * 60)

def main():
    parser = argparse.ArgumentParser(description='Track paper trade outcomes')
    parser.add_argument('--list', action='store_true', help='List unresolved trades')
    parser.add_argument('--report', action='store_true', help='Show PnL report')
    parser.add_argument('--resolve', type=str, help='Resolve a trade by ID')
    parser.add_argument('--outcome', choices=['yes', 'no'], help='Outcome (yes/no)')
    parser.add_argument('--v2', action='store_true', help='Use v2 trades file')
    
    args = parser.parse_args()
    
    v3 = not args.v2
    
    if args.list:
        list_unresolved(v3)
    elif args.report:
        show_report(v3)
    elif args.resolve:
        if not args.outcome:
            print("❌ Must specify --outcome (yes/no)")
            return
        outcome = args.outcome.lower() == 'yes'
        mark_resolved(args.resolve, outcome, v3)
    else:
        parser.print_help()

if __name__ == "__main__":
    main()
