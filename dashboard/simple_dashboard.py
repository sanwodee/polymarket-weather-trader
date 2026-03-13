#!/usr/bin/env python3
"""Simple Flask server for weather trading dashboard"""
import json
import os
from datetime import datetime
from flask import Flask, Response

app = Flask(__name__)

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
TRADES_FILE = os.path.join(SCRIPT_DIR, '../data/positions/paper_trades_v3.jsonl')
LIVE_START_DATE = '2026-03-12'

def load_trades():
    """Load trades from JSONL file"""
    trades = []
    if not os.path.exists(TRADES_FILE):
        return trades
    
    with open(TRADES_FILE, 'r') as f:
        for line in f:
            if not line.strip():
                continue
            try:
                trade = json.loads(line)
                # Add is_live flag based on date
                trade_date = trade.get('timestamp', '')[:10]
                trade['is_live'] = trade_date >= LIVE_START_DATE
                trades.append(trade)
            except:
                continue
    return trades

@app.route('/')
def dashboard():
    """Simple HTML dashboard"""
    try:
        trades = load_trades()
        
        # Calculate basic stats
        paper_trades = [t for t in trades if not t.get('is_live', False)]
        live_trades = [t for t in trades if t.get('is_live', False)]
        
        paper_resolved = [t for t in paper_trades if t.get('resolved')]
        live_resolved = [t for t in live_trades if t.get('resolved')]
        
        paper_pnl = sum(t.get('pnl', 0) or 0 for t in paper_resolved)
        live_pnl = sum(t.get('pnl', 0) or 0 for t in live_resolved)
        
        # Create HTML
        html = f'''<!DOCTYPE html>
<html>
<head>
    <title>Weather Trading Dashboard</title>
    <style>
        body {{ font-family: Arial, sans-serif; margin: 40px; }}
        h1 {{ color: #333; }}
        .section {{ margin: 20px 0; padding: 20px; border: 1px solid #ddd; border-radius: 10px; }}
        .paper {{ background: #f0f0ff; }}
        .live {{ background: #f0fff0; }}
        table {{ width: 100%; border-collapse: collapse; margin-top: 10px; }}
        th, td {{ padding: 8px; text-align: left; border-bottom: 1px solid #ddd; }}
        th {{ background: #eee; }}
        .live-tag {{ color: green; font-weight: bold; }}
        .paper-tag {{ color: purple; font-weight: bold; }}
    </style>
</head>
<body>
    <h1>🌤️ Weather Trading Dashboard</h1>
    <p><em>Last updated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}</em></p>
    
    <div class="section paper">
        <h2>📝 Paper Trading Portfolio</h2>
        <p>Total Trades: {len(paper_trades)} | Resolved: {len(paper_resolved)} | P&L: ${paper_pnl:,.2f}</p>
        <table>
            <tr><th>Date</th><th>Side</th><th>Size</th><th>Status</th><th>P&L</th></tr>
            {''.join(f"<tr><td>{t['timestamp'][:10]}</td><td>{t.get('side','N/A')}</td><td>${t.get('size_usd',0)}</td><td>{'✅ Resolved' if t.get('resolved') else '⏳ Pending'}</td><td>{t.get('pnl','N/A')}</td></tr>" for t in paper_trades[-10:])}
        </table>
    </div>
    
    <div class="section live">
        <h2>💰 Live Trading Portfolio</h2>
        <p>Total Trades: {len(live_trades)} | Resolved: {len(live_resolved)} | P&L: ${live_pnl:,.2f}</p>
        <table>
            <tr><th>Date</th><th>Side</th><th>Size</th><th>Status</th><th>P&L</th></tr>
            {''.join(f"<tr><td>{t['timestamp'][:10]}</td><td>{t.get('side','N/A')}</td><td>${t.get('size_usd',0)}</td><td>{'✅ Resolved' if t.get('resolved') else '⏳ Pending'}</td><td>{t.get('pnl','N/A')}</td></tr>" for t in live_trades)}
        </table>
    </div>
    
    <div class="section">
        <h3>Raw Trade Data</h3>
        <p>Data loaded from: {TRADES_FILE}</p>
        <p>Total trades in database: {len(trades)}</p>
    </div>
</body>
</html>'''
        
        return Response(html, mimetype='text/html')
    except Exception as e:
        import traceback
        error = f"Error: {str(e)}\n\n{traceback.format_exc()}"
        return Response(f'<pre>{error}</pre>', mimetype='text/html', status=500)

if __name__ == '__main__':
    print("Simple Dashboard running on http://localhost:5001/")
    app.run(host='0.0.0.0', port=5001, debug=False)
