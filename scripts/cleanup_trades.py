#!/usr/bin/env python3
"""Clean up paper_trades_v3.jsonl - remove duplicates and cancelled trades"""
import json
import os
from datetime import datetime

# Trades to remove (cancelled non-US cities)
CANCELLED_MARKET_IDS = {
    '0x0b7c394a9ece3693512ddf2ffddf12e587078c7deb8bd0a4114ffcab440e3a74',  # Toronto -8°C
    '0x2f6d38d4e7fa7999dad6eff1d4363b87095f0e0b47b19edbc1a10fa4a8f6b484',  # Toronto -3°C
    '0x10e65244845cfffb6e98040f9c3003de2f18f8fd83ab702aa7a7dda30cd5f0f9',  # London 10°C
}

def clean_trades():
    """Clean the trades file"""
    input_file = 'data/positions/paper_trades_v3.jsonl'
    backup_file = f'data/positions/paper_trades_v3_backup_{datetime.now().strftime("%Y%m%d_%H%M%S")}.jsonl'
    output_file = 'data/positions/paper_trades_v3.jsonl'
    
    if not os.path.exists(input_file):
        print(f"❌ File not found: {input_file}")
        return
    
    # Create backup
    print(f"📁 Creating backup: {backup_file}")
    with open(input_file, 'r') as f_in, open(backup_file, 'w') as f_backup:
        f_backup.write(f_in.read())
    
    # Load and clean
    print("🔍 Loading trades...")
    with open(input_file, 'r') as f:
        lines = f.readlines()
    
    seen_ids = set()
    cleaned_trades = []
    stats = {
        'total': 0,
        'duplicates': 0,
        'cancelled': 0,
        'kept': 0
    }
    
    for line in lines:
        line = line.strip()
        if not line:
            continue
        
        try:
            trade = json.loads(line)
            stats['total'] += 1
            
            trade_id = trade.get('paper_trade_id')
            market_id = trade.get('market_id')
            
            # Skip duplicates
            if trade_id in seen_ids:
                stats['duplicates'] += 1
                print(f"   🗑️ Duplicate: {trade_id[:25]}...")
                continue
            
            # Skip cancelled non-US trades
            if market_id in CANCELLED_MARKET_IDS and not trade.get('resolved', False):
                stats['cancelled'] += 1
                print(f"   🗑️ Cancelled: {trade_id[:25]}... ({market_id[:20]}...)")
                continue
            
            # Keep this trade
            seen_ids.add(trade_id)
            cleaned_trades.append(trade)
            stats['kept'] += 1
            
        except json.JSONDecodeError:
            print(f"   ⚠️ Invalid JSON line, skipping")
            continue
    
    # Write cleaned file
    print(f"\n✍️ Writing cleaned file...")
    with open(output_file, 'w') as f:
        for trade in cleaned_trades:
            f.write(json.dumps(trade) + '\n')
    
    # Summary
    print(f"\n{'='*60}")
    print(f"📊 CLEANUP SUMMARY")
    print(f"{'='*60}")
    print(f"Total lines processed: {stats['total']}")
    print(f"Duplicates removed:     {stats['duplicates']}")
    print(f"Cancelled removed:      {stats['cancelled']}")
    print(f"Trades kept:            {stats['kept']}")
    print(f"\n✅ Cleaned file saved: {output_file}")
    print(f"💾 Backup saved: {backup_file}")
    
    # Show remaining pending trades
    pending = [t for t in cleaned_trades if not t.get('resolved', False)]
    resolved = [t for t in cleaned_trades if t.get('resolved', False)]
    
    print(f"\n📈 CURRENT STATUS:")
    print(f"   Resolved trades: {len(resolved)}")
    print(f"   Pending trades:  {len(pending)}")
    
    if pending:
        total_pending = sum(t.get('size_usd', 0) for t in pending)
        print(f"   Pending exposure: ${total_pending:,.0f}")
        print(f"\n   Pending trades:")
        for t in pending:
            date = t['timestamp'][:10]
            print(f"     • {date}: {t['side']} ${t['size_usd']:,.0f} ({t['paper_trade_id'][:20]}...)")
    
    return stats

if __name__ == '__main__':
    clean_trades()
