#!/usr/bin/env python3
"""
Backtest using actual paper trade outcomes
This analyzes all resolved trades to calculate true model accuracy
"""
import json
import os
from datetime import datetime

def analyze_paper_trades():
    """Analyze actual paper trade performance"""
    trades_file = 'data/positions/paper_trades_v3.jsonl'
    
    if not os.path.exists(trades_file):
        print(f"❌ File not found: {trades_file}")
        return
    
    print("=" * 80)
    print("📊 PAPER TRADE BACKTEST ANALYSIS")
    print("=" * 80)
    
    # Load all trades
    all_trades = []
    with open(trades_file, 'r') as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                trade = json.loads(line)
                all_trades.append(trade)
            except:
                continue
    
    # Remove duplicates
    seen = set()
    unique_trades = []
    for t in all_trades:
        if t['paper_trade_id'] not in seen:
            seen.add(t['paper_trade_id'])
            unique_trades.append(t)
    
    # Separate resolved and pending
    resolved = [t for t in unique_trades if t.get('resolved', False)]
    pending = [t for t in unique_trades if not t.get('resolved', False)]
    
    print(f"\n📈 OVERVIEW")
    print(f"   Total trades:      {len(unique_trades)}")
    print(f"   Resolved:          {len(resolved)}")
    print(f"   Pending:           {len(pending)}")
    
    if not resolved:
        print("\n❌ No resolved trades to analyze")
        return
    
    # Calculate overall stats
    wins = [t for t in resolved if t.get('pnl', 0) > 0]
    losses = [t for t in resolved if t.get('pnl', 0) < 0]
    neutral = [t for t in resolved if t.get('pnl', 0) == 0]
    
    total_pnl = sum(t.get('pnl', 0) for t in resolved)
    win_rate = len(wins) / len(resolved) * 100 if resolved else 0
    
    print(f"\n💰 PERFORMANCE METRICS")
    print(f"   Wins:              {len(wins)}")
    print(f"   Losses:            {len(losses)}")
    print(f"   Breakeven:         {len(neutral)}")
    print(f"   Win Rate:          {win_rate:.1f}%")
    print(f"   Total P&L:         ${total_pnl:+,.0f}")
    
    # Analyze by trade size
    print(f"\n📏 ANALYSIS BY TRADE SIZE")
    size_stats = {}
    for t in resolved:
        size = t.get('size_usd', 0)
        if size not in size_stats:
            size_stats[size] = {'trades': 0, 'wins': 0, 'pnl': 0}
        size_stats[size]['trades'] += 1
        if t.get('pnl', 0) > 0:
            size_stats[size]['wins'] += 1
        size_stats[size]['pnl'] += t.get('pnl', 0)
    
    for size, stats in sorted(size_stats.items()):
        wr = stats['wins'] / stats['trades'] * 100 if stats['trades'] else 0
        print(f"   ${size:,.0f} trades: {stats['wins']}/{stats['trades']} wins ({wr:.0f}%) | P&L: ${stats['pnl']:+,.0f}")
    
    # Analyze by side (YES vs NO)
    print(f"\n🎲 ANALYSIS BY SIDE")
    side_stats = {}
    for t in resolved:
        side = t.get('side', 'UNKNOWN')
        if side not in side_stats:
            side_stats[side] = {'trades': 0, 'wins': 0, 'pnl': 0}
        side_stats[side]['trades'] += 1
        if t.get('pnl', 0) > 0:
            side_stats[side]['wins'] += 1
        side_stats[side]['pnl'] += t.get('pnl', 0)
    
    for side, stats in side_stats.items():
        wr = stats['wins'] / stats['trades'] * 100 if stats['trades'] else 0
        print(f"   {side:10s}: {stats['wins']}/{stats['trades']} wins ({wr:.0f}%) | P&L: ${stats['pnl']:+,.0f}")
    
    # Show all resolved trades chronologically
    print(f"\n📋 ALL RESOLVED TRADES (Chronological)")
    print("-" * 80)
    
    resolved_sorted = sorted(resolved, key=lambda x: x.get('timestamp', ''))
    
    for i, t in enumerate(resolved_sorted, 1):
        date = t.get('timestamp', '?')[:10]
        side = t.get('side', '?')
        size = t.get('size_usd', 0)
        pnl = t.get('pnl', 0)
        outcome = "WIN" if pnl > 0 else "LOSS"
        actual = t.get('actual_temp', '?')
        
        status = "✅" if pnl > 0 else "❌"
        print(f"{status} #{i:2d} {date} | {side:>3s} ${size:>5,.0f} | {outcome:>4s} ${pnl:>+7,.0f} | Actual: {actual}°F")
    
    # Show pending trades
    if pending:
        print(f"\n⏳ PENDING TRADES ({len(pending)})")
        print("-" * 80)
        pending_sorted = sorted(pending, key=lambda x: x.get('timestamp', ''))
        for i, t in enumerate(pending_sorted, 1):
            date = t.get('timestamp', '?')[:10]
            side = t.get('side', '?')
            size = t.get('size_usd', 0)
            market_id = t.get('market_id', '?')[:20]
            print(f"   #{i} {date} | {side:>3s} ${size:>5,.0f} | {market_id}...")
    
    # Key insights
    print(f"\n💡 KEY INSIGHTS")
    print("-" * 80)
    
    if win_rate < 50:
        print("   ⚠️  CRITICAL: Win rate below 50%. Model is not profitable.")
        print("   🛑 DO NOT GO LIVE until win rate improves to 60%+.")
        
        # Analyze why we're losing
        all_yes = [t for t in resolved if t.get('side') == 'YES']
        all_no = [t for t in resolved if t.get('side') == 'NO']
        
        if all_yes:
            yes_losses = [t for t in all_yes if t.get('pnl', 0) < 0]
            print(f"\n   📊 YES trades: {len(all_yes)} trades, {len(yes_losses)} losses ({len(yes_losses)/len(all_yes)*100:.0f}%)")
        
        if all_no:
            no_losses = [t for t in all_no if t.get('pnl', 0) < 0]
            print(f"   📊 NO trades: {len(all_no)} trades, {len(no_losses)} losses ({len(no_losses)/len(all_no)*100:.0f}%)")
        
        # Size analysis
        large_trades = [t for t in resolved if t.get('size_usd', 0) > 1000]
        if large_trades:
            print(f"\n   🚨 Problem: ${len(large_trades)}x trades over $1,000 were all losses")
            print("   💡 Fix: Set hard limit to $500 per trade")
    
    # Recommendations
    print(f"\n📋 RECOMMENDATIONS")
    print("-" * 80)
    
    if win_rate < 40:
        print("   1. 🛑 DO NOT trade live until model improves")
        print("   2. 🔧 Backtest model on 100+ historical markets")
        print("   3. 📊 Identify which cities/market types are problematic")
        print("   4. 🎯 Consider using NO side only (seems less wrong?)")
        print("   5. ⏳ Validate for 2+ weeks of paper trading before live")
    elif win_rate < 55:
        print("   1. ⚠️  Model is marginal - more testing needed")
        print("   2. 💰 If going live: $50 max per trade, $100 daily loss limit")
        print("   3. 🎯 Focus on highest edge trades only (>20%)")
        print("   4. 📊 Paper trade 20+ more markets to improve confidence")
    else:
        print("   1. ✅ Model shows potential")
        print("   2. 💰 Start with $50-100 trades")
        print("   3. 🎯 Scale up gradually if profitable after 20+ trades")
    
    # Monte Carlo simulation
    print(f"\n🎲 MONTE CARLO SIMULATION")
    print("-" * 80)
    
    if resolved:
        import random
        
        # Simulate 1000 runs of 20 trades each
        pnl_list = [t.get('pnl', 0) for t in resolved]
        profits = []
        
        for _ in range(1000):
            # Simulate 20 trades by randomly sampling from history
            sample = [random.choice(pnl_list) for _ in range(20)]
            profits.append(sum(sample))
        
        profits.sort()
        avg_profit = sum(profits) / len(profits)
        median_profit = profits[len(profits)//2]
        worst_5pct = profits[int(len(profits)*0.05)]
        best_5pct = profits[int(len(profits)*0.95)]
        prob_profit = sum(1 for p in profits if p > 0) / len(profits) * 100
        
        print(f"   Simulation: 1000 runs of 20 trades each (sampled from history)")
        print(f"   Average outcome: ${avg_profit:+,.0f}")
        print(f"   Median outcome:  ${median_profit:+,.0f}")
        print(f"   Best 5%:         ${best_5pct:+,.0f}")
        print(f"   Worst 5%:        ${worst_5pct:+,.0f}")
        print(f"   Probability of profit: {prob_profit:.1f}%")
        
        if median_profit < 0:
            print(f"   ⚠️  Expected value is NEGATIVE")
        else:
            print(f"   ✅ Expected value is POSITIVE")

if __name__ == '__main__':
    analyze_paper_trades()
