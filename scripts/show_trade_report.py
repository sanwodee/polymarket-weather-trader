#!/usr/bin/env python3
import json
from datetime import datetime

# Load trades
trades_file = 'data/positions/paper_trades_v3.jsonl'
print('='*60)
print('📊 TRADE RESOLUTION REPORT - March 6, 2026')
print('='*60)

trades = []
with open(trades_file, 'r') as f:
    for line in f:
        if line.strip():
            trades.append(json.loads(line))

# Filter for trades resolved today
today = '2026-03-06'
resolved_today = [t for t in trades if t.get('resolved') and t.get('resolved_at', '').startswith(today)]
pending = [t for t in trades if not t.get('resolved', False)]

print(f'\n📈 SUMMARY')
print(f'   Total trades: {len(trades)}')
print(f'   Resolved today: {len(resolved_today)}')
print(f'   Still pending: {len(pending)}')

if resolved_today:
    total_pnl = sum(t.get('pnl', 0) for t in resolved_today)
    print(f"\n💰 TODAY'S P&L: ${total_pnl:+,.0f}")
    print(f'\n📋 Resolved Trades:')
    for t in resolved_today:
        print(f"\n   Trade: {t['paper_trade_id'][:25]}...")
        print(f"   Side: {t['side']} | Size: ${t['size_usd']:,.0f}")
        print(f"   Actual Temp: {t.get('actual_temp', 'N/A')}°F")
        outcome = 'WIN' if t.get('pnl', 0) > 0 else 'LOSS'
        print(f"   Outcome: {outcome}")
        print(f"   P&L: ${t.get('pnl', 0):+,.0f}")
else:
    print(f"\nℹ️ No trades were resolved today (March 6).")
    print(f'   Pending trades: {len(pending)}')

# Show pending trades
if pending:
    print(f'\n⏳ Pending Trades ({len(pending)}):')
    for t in pending[:3]:
        print(f"   - {t['paper_trade_id'][:25]}... (${t['size_usd']:,.0f} {t['side']})")

print(f"\n{'='*60}")

# Overall stats
all_resolved = [t for t in trades if t.get('resolved')]
if all_resolved:
    total_pnl = sum(t.get('pnl', 0) for t in all_resolved)
    wins = len([t for t in all_resolved if t.get('pnl', 0) > 0])
    losses = len([t for t in all_resolved if t.get('pnl', 0) < 0])
    win_rate = wins / len(all_resolved) * 100 if all_resolved else 0
    print(f'📊 ALL-TIME STATS')
    print(f'   Total Resolved: {len(all_resolved)}')
    print(f'   Wins: {wins} | Losses: {losses}')
    print(f'   Win Rate: {win_rate:.1f}%')
    print(f'   Total P&L: ${total_pnl:+,.0f}')
