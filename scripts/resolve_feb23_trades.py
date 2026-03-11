#!/usr/bin/env python3
"""
Resolve Feb 23 trades with actual weather data
"""
import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

from evaluator.outcome_tracker import mark_trade_resolved, load_trades, calculate_performance

# Actual weather on Feb 23, 2026:
# Chicago: High was 26.1°F (-3.3°C)
# NYC: Snow was 5.1 inches (12.95 cm)

ACTUAL_WEATHER = {
    'chicago_temp': 26.1,  # °F
    'nyc_snow': 5.1       # inches
}

# Map market IDs to thresholds
MARKET_THRESHOLDS = {
    '0x833c4acb5213daf0ff29a5d21b0f563e6a14c1c85609392ca6a58860d2699d58': {'type': 'snow', 'range': (8, 10), 'city': 'NYC'},
    '0x09acdae4ba83fc6a0c1e7045179c0f5081a2db993b25ac20610ba38569365326': {'type': 'snow', 'range': (10, 12), 'city': 'NYC'},
    '0x331e0cc96cca3a3147e68bb35247b94372793cb6bf852eeae515bb5f998c07e2': {'type': 'temp', 'range': (30, 31), 'city': 'Chicago'},
    '0x33745c7d26e084d71f7ea8cd36c45196906c3cd9e8a4ddc63a57c7fcfbc2b9b0': {'type': 'temp', 'range': (32, 33), 'city': 'Chicago'},
    '0x2cc5e0cbf2136fdf131186ade443e032485c1f94e0e2f2d6605e5363760ebd03': {'type': 'temp', 'range': (34, 35), 'city': 'Chicago'},
    '0x354f295d593a060c991aa4cafb09c4c02284eb464f23b9df55b140f360376114': {'type': 'temp', 'range': (36, 37), 'city': 'Chicago'},
    '0xaaf0b7a05e35d14d86d009a7c3a9b051c7a5ab2b6a0d8821491469ebae21adb9': {'type': 'temp', 'range': (38, 39), 'city': 'Chicago'},
    '0xb9620c9a6ef6dc77ea013fb5bc765e72a9f58d784182c1642f0b5b702e9ce0e3': {'type': 'temp', 'range': (36, 37), 'city': 'Chicago', 'end_date': '2026-02-24'},
}

def check_outcome(market_id, threshold_info):
    """Determine if the outcome was YES or NO"""
    t_type = threshold_info['type']
    low, high = threshold_info['range']
    
    if t_type == 'snow':
        # NYC snow: 8-10" or 10-12"
        actual = ACTUAL_WEATHER['nyc_snow']
        in_range = low <= actual <= high
        return in_range
    else:  # temp
        # Chicago temp ranges
        actual = ACTUAL_WEATHER['chicago_temp']
        in_range = low <= actual <= high
        return in_range

def resolve_feb23_trades():
    """Mark all Feb 23 trades as resolved"""
    print("📊 Resolving Feb 23 Trades")
    print("=" * 60)
    print(f"\nActual Weather Feb 23, 2026:")
    print(f"  Chicago High: {ACTUAL_WEATHER['chicago_temp']}°F")
    print(f"  NYC Snow: {ACTUAL_WEATHER['nyc_snow']} inches")
    print()
    
    # Load old trades
    old_trades_file = 'data/positions/paper_trades.jsonl'
    trades = []
    if os.path.exists(old_trades_file):
        with open(old_trades_file, 'r') as f:
            for line in f:
                trades.append(json.loads(line.strip()))
    
    # Process only Feb 23 trades (before today)
    feb23_trades = [t for t in trades if '2026-02-23' in t.get('timestamp', '')]
    
    if not feb23_trades:
        print("No Feb 23 trades found")
        return
    
    print(f"Found {len(feb23_trades)} trades from Feb 23")
    print()
    
    # Results summary
    results = []
    total_pnl = 0
    wins = 0
    losses = 0
    
    # Process each trade
    for trade in feb23_trades:
        trade_id = trade['paper_trade_id']
        market_id = trade['market_id']
        side = trade['side']
        size = trade.get('size_usd', 0)
        
        # Get threshold info
        threshold = MARKET_THRESHOLDS.get(market_id)
        if not threshold:
            print(f"⚠️  Unknown market: {market_id[:30]}...")
            continue
        
        # Check actual outcome
        outcome_yes = check_outcome(market_id, threshold)
        
        # Determine win/loss
        if side == 'YES':
            won = outcome_yes
        else:
            won = not outcome_yes
        
        # Calculate PnL (rough estimate: 4% fees + win/loss)
        fees = size * 0.04
        if won:
            pnl = size - fees  # Win: get stake back minus fees
        else:
            pnl = -size - fees  # Lose: lost stake plus fees
        
        results.append({
            'trade_id': trade_id,
            'market': f"{threshold['city']} {threshold['type']} {threshold['range']}",
            'side': side,
            'size': size,
            'actual': f"{ACTUAL_WEATHER['chicago_temp'] if threshold['type']=='temp' else ACTUAL_WEATHER['nyc_snow']}",
            'in_range': outcome_yes,
            'won': won,
            'pnl': pnl
        })
        
        if won:
            wins += 1
        else:
            losses += 1
        total_pnl += pnl
    
    # Print results
    print("Resolution Results:")
    print("-" * 60)
    for r in results:
        status = "✅ WIN" if r['won'] else "❌ LOSS"
        print(f"\n{r['trade_id'][:20]}...")
        print(f"  Market: {r['market']}")
        print(f"  Bet: {r['side']} ${r['size']:,.0f}")
        print(f"  Actual: {r['actual']} → Range hit: {r['in_range']}")
        print(f"  Result: {status}")
        print(f"  PnL: ${r['pnl']:,.0f}")
    
    print()
    print("=" * 60)
    print("📊 Summary")
    print("=" * 60)
    print(f"Total Trades: {len(results)}")
    print(f"Wins: {wins} | Losses: {losses}")
    print(f"Win Rate: {wins/len(results)*100:.1f}%" if results else "N/A")
    print(f"Total PnL: ${total_pnl:,.2f}")
    print(f"Avg PnL per trade: ${total_pnl/len(results):,.2f}" if results else "N/A")
    
    # Save summary
    summary = {
        'date': '2026-02-23',
        'trades_resolved': len(results),
        'wins': wins,
        'losses': losses,
        'total_pnl': round(total_pnl, 2),
        'actual_weather': ACTUAL_WEATHER
    }
    
    summary_file = 'data/positions/feb23_resolution.json'
    os.makedirs(os.path.dirname(summary_file), exist_ok=True)
    with open(summary_file, 'w') as f:
        json.dump(summary, f, indent=2)
    
    print(f"\n💾 Saved to {summary_file}")

if __name__ == "__main__":
    resolve_feb23_trades()
