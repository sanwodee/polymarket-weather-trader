#!/usr/bin/env python3
"""Manual resolution for Feb 25-27 and Mar 1 pending trades"""
import json
import os
from datetime import datetime

# Known outcomes based on historical weather data
# Source: Open-Meteo historical API or NOAA
trade_outcomes = {
    # Feb 25, 2026 - Need to determine
    'paper_20260225160513': {
        'date': '2026-02-25',
        'city': 'unknown',
        'resolved': False,  # Unknown outcome - need data
        'note': 'Feb 25 market data not available'
    },
    # Feb 27, 2026 - Atlanta 76°F
    'paper_20260227093428': {
        'date': '2026-02-27',
        'city': 'atlanta',
        'actual_temp': 65.5,  # From Open-Meteo historical
        'outcome': False,  # 65.5°F < 76°F
        'side': 'YES',
        'size': 500,
        'pnl': -520  # Lose full $500 + $20 fees
    },
    'paper_20260227093543': {
        'date': '2026-02-27',
        'city': 'atlanta',
        'actual_temp': 65.5,  # Same market, same outcome
        'outcome': False,
        'side': 'YES',
        'size': 500,
        'pnl': -520
    },
    # Mar 1, 2026 - Atlanta 76°F
    'paper_20260301141836': {
        'date': '2026-03-01',
        'city': 'atlanta',
        'actual_temp': 74.4,  # From Open-Meteo historical
        'outcome': False,  # 74.4°F < 76°F
        'side': 'YES',
        'size': 500,
        'pnl': -520  # Lose full $500 + $20 fees
    }
}

# Adjust P&L for fees (4% total)
for trade_id, data in trade_outcomes.items():
    if data.get('resolved', True) and 'pnl' in data:
        if data['pnl'] > 0:
            # Winner: pay 4% fees on profit
            gross_win = data['size']
            fees = data['size'] * 0.04
            data['pnl'] = gross_win - fees
        else:
            # Loser: lose full amount + fees already deducted on entry
            pass

def manual_resolve():
    """Manually resolve trades with known outcomes"""
    trades_file = 'data/positions/paper_trades_v3.jsonl'
    
    with open(trades_file, 'r') as f:
        lines = f.readlines()
    
    trades = []
    resolved_count = 0
    skipped_count = 0
    
    for line in lines:
        line = line.strip()
        if not line:
            continue
        
        trade = json.loads(line)
        trade_id = trade['paper_trade_id']
        
        # Skip if already resolved
        if trade.get('resolved', False):
            trades.append(trade)
            continue
        
        # Check if we have outcome data
        if trade_id in trade_outcomes:
            outcome_data = trade_outcomes[trade_id]
            
            if not outcome_data.get('resolved', True):
                print(f"⏸️  {trade_id}: {outcome_data['note']}")
                trades.append(trade)
                skipped_count += 1
                continue
            
            # Resolve the trade
            trade['resolved'] = True
            trade['actual_outcome'] = outcome_data['outcome']
            trade['actual_temp'] = outcome_data['actual_temp']
            trade['pnl'] = outcome_data['pnl']
            trade['resolved_at'] = datetime.now().isoformat()
            trade['resolution_source'] = 'manual_historical_weather'
            
            trades.append(trade)
            resolved_count += 1
            
            print(f"✅ {trade_id}: {outcome_data['city']} | {outcome_data['actual_temp']}°F")
            print(f"   Outcome: {outcome_data['outcome']} | P&L: ${outcome_data['pnl']:,.0f}")
        else:
            trades.append(trade)
            skipped_count += 1
    
    # Write back
    with open(trades_file, 'w') as f:
        for trade in trades:
            f.write(json.dumps(trade) + '\n')
    
    print(f"\n{'='*60}")
    print(f"📊 RESOLUTION COMPLETE")
    print(f"{'='*60}")
    print(f"Resolved: {resolved_count}")
    print(f"Skipped:  {skipped_count}")
    
    # Summary
    resolved = [t for t in trades if t.get('resolved', False)]
    pending = [t for t in trades if not t.get('resolved', False)]
    total_pnl = sum(t.get('pnl', 0) or 0 for t in resolved)
    
    print(f"\n📈 Portfolio Status:")
    print(f"   Total trades: {len(trades)}")
    print(f"   Resolved:     {len(resolved)}")
    print(f"   Pending:      {len(pending)}")
    print(f"   Total P&L:    ${total_pnl:+,.0f}")
    
    if pending:
        print(f"\n   Still pending:")
        for t in pending:
            print(f"     - {t['paper_trade_id'][:30]}... ${t['size_usd']:,.0f}")

if __name__ == '__main__':
    manual_resolve()
