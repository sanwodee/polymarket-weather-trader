#!/usr/bin/env python3
"""Simple Flask server for weather trading dashboard with full stats"""
import json
import os
import re
from datetime import datetime
from flask import Flask, Response

app = Flask(__name__)

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
TRADES_FILE = os.path.join(SCRIPT_DIR, '../data/positions/paper_trades_v3.jsonl')
LIVE_START_DATE = '2026-03-12'

# City uncertainty mapping (from research)
CITY_UNCERTAINTY = {
    'seattle': 3.8, 'chicago': 2.5, 'miami': 1.5,
    'atlanta': 2.0, 'dallas': 2.5, 'phoenix': 2.0,
    'denver': 4.5, 'boston': 3.0, 'houston': 2.5,
}

def extract_city(question):
    """Extract city from market question"""
    if not question:
        return "Unknown"
    q_lower = question.lower()
    for city in CITY_UNCERTAINTY.keys():
        if city in q_lower:
            return city.title()
    return "Unknown"

def load_trades():
    """Load trades from JSONL file"""
    trades = []
    seen = set()
    
    if not os.path.exists(TRADES_FILE):
        return trades
    
    with open(TRADES_FILE, 'r') as f:
        for line in f:
            if not line.strip():
                continue
            try:
                trade = json.loads(line)
                # Deduplication
                trade_id = trade.get('paper_trade_id', '')
                market_id = trade.get('market_id', '')
                unique_key = f"{trade_id}_{market_id}"
                
                if unique_key in seen:
                    continue
                seen.add(unique_key)
                
                # Add is_live flag and city
                trade_date = trade.get('timestamp', '')[:10]
                trade['is_live'] = trade_date >= LIVE_START_DATE
                trade['city'] = extract_city(trade.get('market_question', ''))
                
                trades.append(trade)
            except:
                continue
    return trades

def calculate_stats(trades):
    """Calculate comprehensive stats for paper and live trades"""
    
    # Separate paper and live
    paper_trades = [t for t in trades if not t.get('is_live', False)]
    live_trades = [t for t in trades if t.get('is_live', False)]
    
    # Paper stats
    paper_resolved = [t for t in paper_trades if t.get('resolved')]
    paper_pending = [t for t in paper_trades if not t.get('resolved')]
    paper_wins = sum(1 for t in paper_resolved if t.get('pnl', 0) > 0)
    paper_losses = sum(1 for t in paper_resolved if t.get('pnl', 0) < 0)
    paper_win_rate = (paper_wins / len(paper_resolved) * 100) if paper_resolved else 0
    paper_pnl = sum(t.get('pnl', 0) or 0 for t in paper_resolved)
    paper_exposure = sum(t.get('size_usd', 0) for t in paper_trades)
    
    # Live stats
    live_resolved = [t for t in live_trades if t.get('resolved')]
    live_pending = [t for t in live_trades if not t.get('resolved')]
    live_wins = sum(1 for t in live_resolved if t.get('pnl', 0) > 0)
    live_losses = sum(1 for t in live_resolved if t.get('pnl', 0) < 0)
    live_win_rate = (live_wins / len(live_resolved) * 100) if live_resolved else 0
    live_pnl = sum(t.get('pnl', 0) or 0 for t in live_resolved)
    live_exposure = sum(t.get('size_usd', 0) for t in live_trades)
    
    # Combined
    total_pnl = paper_pnl + live_pnl
    all_resolved = paper_resolved + live_resolved
    total_wins = paper_wins + live_wins
    total_losses = paper_losses + live_losses
    total_win_rate = (total_wins / len(all_resolved) * 100) if all_resolved else 0
    
    return {
        'paper': {
            'total': len(paper_trades),
            'resolved': len(paper_resolved),
            'pending': len(paper_pending),
            'wins': paper_wins,
            'losses': paper_losses,
            'win_rate': paper_win_rate,
            'pnl': paper_pnl,
            'exposure': paper_exposure,
            'trades': paper_trades
        },
        'live': {
            'total': len(live_trades),
            'resolved': len(live_resolved),
            'pending': len(live_pending),
            'wins': live_wins,
            'losses': live_losses,
            'win_rate': live_win_rate,
            'pnl': live_pnl,
            'exposure': live_exposure,
            'trades': live_trades
        },
        'combined': {
            'total': len(trades),
            'win_rate': total_win_rate,
            'pnl': total_pnl
        }
    }

def generate_trade_row(t):
    """Generate HTML for a single trade row"""
    date = t.get('timestamp', '')[:10]
    side = t.get('side', 'N/A')
    size = t.get('size_usd', 0)
    city = t.get('city', 'Unknown')
    resolved = t.get('resolved', False)
    pnl = t.get('pnl')
    
    if resolved and pnl is not None:
        pnl_class = 'win' if pnl >= 0 else 'loss'
        pnl_text = f"+${pnl:,.0f}" if pnl >= 0 else f"-${abs(pnl):,.0f}"
        status = '✅ Win' if pnl > 0 else '❌ Loss'
    else:
        pnl_class = 'pending'
        pnl_text = 'Pending'
        status = '⏳ Pending'
    
    return f'''
    <tr>
        <td>{date}</td>
        <td><strong>{city}</strong> {side}</td>
        <td>${size}</td>
        <td>{status}</td>
        <td class="{pnl_class}">{pnl_text}</td>
    </tr>
    '''

@app.route('/')
def dashboard():
    """Generate full-featured dashboard"""
    try:
        trades = load_trades()
        stats = calculate_stats(trades)
        
        updated_time = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        
        html = f'''<!DOCTYPE html>
<html>
<head>
    <title>Weather Trading Dashboard</title>
    <style>
        body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; 
               margin: 0; padding: 20px; background: #f5f5f5; }}
        .container {{ max-width: 1200px; margin: 0 auto; }}
        h1 {{ color: #333; margin-bottom: 10px; }}
        .subtitle {{ color: #666; margin-bottom: 30px; }}
        
        .stats-grid {{ display: grid; grid-template-columns: repeat(4, 1fr); gap: 15px; margin-bottom: 30px; }}
        .stat-card {{ background: white; padding: 20px; border-radius: 10px; box-shadow: 0 2px 4px rgba(0,0,0,0.1); }}
        .stat-label {{ color: #666; font-size: 12px; text-transform: uppercase; margin-bottom: 5px; }}
        .stat-value {{ font-size: 28px; font-weight: bold; color: #333; }}
        .stat-value.win {{ color: #00C805; }}
        .stat-value.loss {{ color: #FF5000; }}
        
        .section {{ background: white; border-radius: 10px; padding: 20px; margin-bottom: 20px;
                   box-shadow: 0 2px 4px rgba(0,0,0,0.1); }}
        .section.paper {{ border-left: 4px solid #8b5cf6; }}
        .section.live {{ border-left: 4px solid #00C805; }}
        
        .section-header {{ display: flex; justify-content: space-between; align-items: center;
                          margin-bottom: 15px; padding-bottom: 15px; border-bottom: 1px solid #eee; }}
        .section-title {{ font-size: 20px; font-weight: bold; margin: 0; }}
        .section-title.paper {{ color: #8b5cf6; }}
        .section-title.live {{ color: #00C805; }}
        
        .section-stats {{ display: flex; gap: 20px; font-size: 14px; color: #666; }}
        
        table {{ width: 100%; border-collapse: collapse; margin-top: 15px; }}
        th {{ background: #f8f8f8; padding: 12px; text-align: left; font-weight: 600;
              color: #333; font-size: 13px; border-bottom: 2px solid #eee; }}
        td {{ padding: 12px; border-bottom: 1px solid #eee; font-size: 14px; }}
        tr:hover {{ background: #f8f8f8; }}
        
        .win {{ color: #00C805; font-weight: 600; }}
        .loss {{ color: #FF5000; font-weight: 600; }}
        .pending {{ color: #666; }}
        
        .footer {{ margin-top: 30px; padding-top: 20px; border-top: 1px solid #ddd;
                  text-align: center; color: #999; font-size: 12px; }}
    </style>
</head>
<body>
    <div class="container">
        <h1>🌤️ Weather Trading Dashboard</h1>
        <p class="subtitle">Last updated: {updated_time} | Data loads fresh on every refresh</p>
        
        <!-- Overall Stats -->
        <div class="stats-grid">
            <div class="stat-card">
                <div class="stat-label">Total P&L</div>
                <div class="stat-value {'win' if stats['combined']['pnl'] >= 0 else 'loss'}">
                    {'+$' if stats['combined']['pnl'] >= 0 else '-$'}{abs(stats['combined']['pnl']):,.0f}
                </div>
            </div>
            <div class="stat-card">
                <div class="stat-label">Total Trades</div>
                <div class="stat-value">{stats['combined']['total']}</div>
            </div>
            <div class="stat-card">
                <div class="stat-label">Win Rate</div>
                <div class="stat-value">{stats['combined']['win_rate']:.1f}%</div>
            </div>
            <div class="stat-card">
                <div class="stat-label">Data Source</div>
                <div class="stat-value" style="font-size: 14px; color: #666;">paper_trades_v3.jsonl</div>
            </div>
        </div>
        
        <!-- Live Trading Section -->
        <div class="section live">
            <div class="section-header">
                <div>
                    <h2 class="section-title live">💰 Live Trading (March 12+)</h2>
                </div>
                <div class="section-stats">
                    <span>{stats['live']['total']} trades</span>
                    <span>{stats['live']['resolved']} resolved</span>
                    <span>{stats['live']['pending']} pending</span>
                    <span>{stats['live']['wins']}W / {stats['live']['losses']}L</span>
                    <span>{stats['live']['win_rate']:.1f}% win rate</span>
                </div>
            </div>
            <div style="font-size: 18px; font-weight: bold; color: {'#00C805' if stats['live']['pnl'] >= 0 else '#FF5000'}; margin-bottom: 15px;">
                Net P&L: {'+$' if stats['live']['pnl'] >= 0 else '-$'}{abs(stats['live']['pnl']):,.0f}
            </div>
            <table>
                <thead>
                    <tr>
                        <th>Date</th>
                        <th>Trade</th>
                        <th>Size</th>
                        <th>Status</th>
                        <th>P&L</th>
                    </tr>
                </thead>
                <tbody>
                    {''.join(generate_trade_row(t) for t in reversed(stats['live']['trades'])) if stats['live']['trades'] else '<tr><td colspan="5" style="text-align: center; color: #999;">No live trades yet</td></tr>'}
                </tbody>
            </table>
        </div>
        
        <!-- Paper Trading Section -->
        <div class="section paper">
            <div class="section-header">
                <div>
                    <h2 class="section-title paper">📝 Paper Trading (Before March 12)</h2>
                </div>
                <div class="section-stats">
                    <span>{stats['paper']['total']} trades</span>
                    <span>{stats['paper']['resolved']} resolved</span>
                    <span>{stats['paper']['pending']} pending</span>
                    <span>{stats['paper']['wins']}W / {stats['paper']['losses']}L</span>
                    <span>{stats['paper']['win_rate']:.1f}% win rate</span>
                </div>
            </div>
            <div style="font-size: 18px; font-weight: bold; color: {'#00C805' if stats['paper']['pnl'] >= 0 else '#FF5000'}; margin-bottom: 15px;">
                Net P&L: {'+$' if stats['paper']['pnl'] >= 0 else '-$'}{abs(stats['paper']['pnl']):,.0f}
            </div>
            <table>
                <thead>
                    <tr>
                        <th>Date</th>
                        <th>Trade</th>
                        <th>Size</th>
                        <th>Status</th>
                        <th>P&L</th>
                    </tr>
                </thead>
                <tbody>
                    {''.join(generate_trade_row(t) for t in reversed(stats['paper']['trades'])) if stats['paper']['trades'] else '<tr><td colspan="5" style="text-align: center; color: #999;">No paper trades</td></tr>'}
                </tbody>
            </table>
        </div>
        
        <div class="footer">
            Data loaded from {TRADES_FILE} | 
            Live trades identified by date >= {LIVE_START_DATE} | 
            Auto-refreshes on every page load
        </div>
    </div>
</body>
</html>'''
        
        return Response(html, mimetype='text/html')
    except Exception as e:
        import traceback
        error_html = f'''
        <html><body style="font-family: monospace; padding: 20px;">
        <h1 style="color: red;">Dashboard Error</h1>
        <pre style="background: #f5f5f5; padding: 20px; border-radius: 5px;">{traceback.format_exc()}</pre>
        </body></html>
        '''
        return Response(error_html, mimetype='text/html', status=500)

if __name__ == '__main__':
    print("Dashboard with full stats running on http://0.0.0.0:5001/")
    app.run(host='0.0.0.0', port=5001, debug=False)
