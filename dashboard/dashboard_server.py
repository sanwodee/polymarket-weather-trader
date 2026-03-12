#!/usr/bin/env python3
"""Flask server that serves Robinhood-style dashboard - regenerates on each request"""
import json
import os
import sys
from datetime import datetime
from flask import Flask, Response

app = Flask(__name__)

# Get the absolute path to trades file
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
TRADES_FILE = os.path.join(SCRIPT_DIR, '../data/positions/paper_trades_v3.jsonl')

def load_trades():
    """Load trades from JSONL file"""
    trades = []
    seen = set()
    
    # Check multiple possible locations
    possible_paths = [
        TRADES_FILE,
        os.path.join(SCRIPT_DIR, 'data/positions/paper_trades_v3.jsonl'),
        '../data/positions/paper_trades_v3.jsonl',
        'data/positions/paper_trades_v3.jsonl',
    ]
    
    for path in possible_paths:
        if os.path.exists(path):
            with open(path, 'r') as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        trade = json.loads(line)
                        # Use composite key: paper_trade_id + market_id for uniqueness
                        unique_key = f"{trade.get('paper_trade_id', '')}_{trade.get('market_id', '')}"
                        if unique_key not in seen:
                            seen.add(unique_key)
                            trades.append(trade)
                    except json.JSONDecodeError:
                        continue
            break
    
    return trades

def calculate_stats(trades):
    """Calculate dashboard statistics"""
    total_trades = len(trades)
    total_exposure = sum(t.get('size_usd', 0) for t in trades)
    
    resolved = [t for t in trades if t.get('resolved', False)]
    pending = [t for t in trades if not t.get('resolved', False)]
    
    wins = sum(1 for t in resolved if t.get('pnl', 0) > 0)
    losses = sum(1 for t in resolved if t.get('pnl', 0) < 0)
    win_rate = (wins / len(resolved) * 100) if resolved else 0
    
    total_pnl = sum(t.get('pnl', 0) or 0 for t in resolved)
    
    # Group resolved trades by date
    daily_stats = {}
    for t in resolved:
        date = datetime.fromisoformat(t['timestamp'].replace('Z', '+00:00')).strftime('%Y-%m-%d')
        if date not in daily_stats:
            daily_stats[date] = {'trades': [], 'pnl': 0, 'wins': 0, 'losses': 0}
        daily_stats[date]['trades'].append(t)
        daily_stats[date]['pnl'] += t.get('pnl', 0) or 0
        if t.get('pnl', 0) > 0:
            daily_stats[date]['wins'] += 1
        else:
            daily_stats[date]['losses'] += 1
    
    return {
        'total_trades': total_trades,
        'total_exposure': total_exposure,
        'resolved_count': len(resolved),
        'pending_count': len(pending),
        'wins': wins,
        'losses': losses,
        'win_rate': win_rate,
        'total_pnl': total_pnl,
        'resolved': resolved,
        'pending': pending,
        'daily_stats': daily_stats
    }

def format_trade_card(t, status_type):
    """Generate a Robinhood-style trade card"""
    date = datetime.fromisoformat(t['timestamp'].replace('Z', '+00:00')).strftime('%b %d')
    side = t['side']
    size = t['size_usd']
    shares = t.get('shares', 0)
    
    if status_type == 'resolved':
        pnl = t.get('pnl', 0) or 0
        is_win = pnl > 0
        card_class = 'win' if is_win else 'loss'
        pnl_class = 'win' if is_win else 'loss'
        pnl_text = f"+${pnl:,.0f}" if is_win else f"-${abs(pnl):,.0f}"
        status_html = f'<span class="status status-{ "win" if is_win else "loss" }"><span class="status-dot"></span>{"Win" if is_win else "Loss"}</span>'
        pnl_display = f'<div class="trade-pnl {pnl_class}">{pnl_text}</div>'
        actual_temp = t.get('actual_temp', '-')
        meta = f"{date} • {shares:,} shares • Actual: {actual_temp}°F"
    else:
        card_class = ''
        exp_profit = t.get('expected_net_profit', 0)
        status_html = '<span class="status status-pending"><span class="status-dot"></span>Pending</span>'
        pnl_display = '<div class="trade-pnl pending">Awaiting</div>'
        meta = f"{date} • {shares:,} shares • Expected: +${exp_profit:,.0f}"
    
    return f'''
    <div class="trade-card {card_class}">
        <div class="trade-left">
            <div class="trade-symbol">{side} ${size:,.0f}</div>
            <div class="trade-meta">{meta}</div>
        </div>
        <div class="trade-right">
            {pnl_display}
            {status_html}
        </div>
    </div>
    '''

def format_daily_summary_card(date_str, day_data):
    """Generate a daily summary card with nested trades"""
    date_display = datetime.strptime(date_str, '%Y-%m-%d').strftime('%b %d, %Y')
    daily_pnl = day_data['pnl']
    num_trades = len(day_data['trades'])
    wins = day_data['wins']
    losses = day_data['losses']
    
    is_profit = daily_pnl >= 0
    summary_class = 'win' if is_profit else 'loss'
    pnl_text = f"+${daily_pnl:,.0f}" if is_profit else f"-${abs(daily_pnl):,.0f}"
    
    # Generate nested trade cards for this day (compact view)
    trade_cards = ""
    for t in day_data['trades']:
        side = t['side']
        size = t['size_usd']
        pnl = t.get('pnl', 0) or 0
        is_trade_win = pnl > 0
        trade_pnl_text = f"+${pnl:,.0f}" if is_trade_win else f"-${abs(pnl):,.0f}"
        trade_pnl_class = 'win' if is_trade_win else 'loss'
        actual_temp = t.get('actual_temp', '-')
        
        trade_cards += f'''
        <div class="nested-trade">
            <div class="nested-left">
                <span class="nested-symbol">{side} ${size:,.0f}</span>
                <span class="nested-meta">Actual: {actual_temp}°F</span>
            </div>
            <div class="nested-pnl {trade_pnl_class}">{trade_pnl_text}</div>
        </div>
        '''
    
    return f'''
    <div class="daily-summary {summary_class}">
        <div class="daily-header">
            <div class="daily-left">
                <div class="daily-date">{date_display}</div>
                <div class="daily-meta">{num_trades} trades • {wins}W/{losses}L</div>
            </div>
            <div class="daily-right">
                <div class="daily-pnl {summary_class}">{pnl_text}</div>
                <span class="status status-{'win' if is_profit else 'loss'}"><span class="status-dot"></span>{'Daily Profit' if is_profit else 'Daily Loss'}</span>
            </div>
        </div>
        <div class="daily-trades">
            {trade_cards}
        </div>
    </div>
    '''

def generate_table_row(t):
    """Generate a table row for the complete history"""
    date = datetime.fromisoformat(t['timestamp'].replace('Z', '+00:00')).strftime('%b %d')
    is_resolved = t.get('resolved', False)
    pnl = t.get('pnl')
    
    if is_resolved and pnl is not None:
        pnl_display = f"+${pnl:,.0f}" if pnl >= 0 else f"-${abs(pnl):,.0f}"
        pnl_style = f'color: var(--rh-{"green" if pnl >= 0 else "red"}); font-weight: 600;'
        status_class = 'status-win' if pnl >= 0 else 'status-loss'
        status_text = 'Win' if pnl >= 0 else 'Loss'
    else:
        pnl_display = '-'
        pnl_style = 'color: var(--rh-gray-500);'
        status_class = 'status-pending'
        status_text = 'Pending'
    
    return f'''
    <tr>
        <td>{date}</td>
        <td><code class="trade-id">{t['paper_trade_id'][:20]}...</code></td>
        <td>{t['side']}</td>
        <td>${t['size_usd']:,.0f}</td>
        <td>{t['shares']:,}</td>
        <td>+${t.get('expected_net_profit', 0):,.0f}</td>
        <td><span class="status {status_class}"><span class="status-dot"></span>{status_text}</span></td>
        <td style="text-align: right; {pnl_style}">{pnl_display}</td>
    </tr>
    '''

def generate_html(trades, stats):
    """Generate Robinhood-style HTML"""
    
    pnl_is_positive = stats['total_pnl'] >= 0
    portfolio_change_class = 'change-positive' if pnl_is_positive else 'change-negative'
    portfolio_value = f"+${stats['total_pnl']:,.0f}" if pnl_is_positive else f"-${abs(stats['total_pnl']):,.0f}"
    
    # Calculate return percentage
    exposure_factor = stats['total_exposure'] if stats['total_exposure'] > 0 else 1
    return_pct = (stats['total_pnl'] / exposure_factor) * 100 if exposure_factor > 0 else 0
    
    # Generate daily summary cards (sorted by date descending)
    daily_cards = ""
    sorted_dates = sorted(stats['daily_stats'].keys(), reverse=True)
    for date in sorted_dates:
        day_data = stats['daily_stats'][date]
        daily_cards += format_daily_summary_card(date, day_data)
    
    if not daily_cards:
        daily_cards = '<div style="text-align: center; padding: 40px; color: var(--rh-gray-500);">No resolved trades yet.</div>'
    
    # Generate cards and rows
    pending_cards = ''.join(format_trade_card(t, 'pending') for t in reversed(stats['pending']))
    if not pending_cards:
        pending_cards = '<div style="text-align: center; padding: 40px; color: var(--rh-gray-500);">No pending trades.</div>'
    
    table_rows = ''.join(generate_table_row(t) for t in reversed(trades))
    
    updated_time = datetime.now().strftime('%b %-d, %I:%M %p')
    generated_time = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    
    html = f'''<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Weather Trading Dashboard</title>
    <style>
        @import url('https://fonts.googleapis.com/css2?family=DM+Sans:wght@400;500;700&display=swap');
        
        :root {{
            --rh-green: #00C805;
            --rh-green-light: #E6F9E6;
            --rh-red: #FF5000;
            --rh-red-light: #FFF0EB;
            --rh-black: #000000;
            --rh-white: #FFFFFF;
            --rh-gray-100: #F5F8FA;
            --rh-gray-200: #E3E9ED;
            --rh-gray-300: #CFD8DC;
            --rh-gray-500: #8F9BB3;
            --rh-gray-700: #2E3A59;
            --rh-blue: #0051FF;
        }}
        
        * {{ margin: 0; padding: 0; box-sizing: border-box; }}
        
        body {{
            font-family: 'DM Sans', -apple-system, BlinkMacSystemFont, sans-serif;
            background: var(--rh-white);
            color: var(--rh-black);
            min-height: 100vh;
            line-height: 1.5;
        }}
        
        .header {{
            background: var(--rh-white);
            border-bottom: 1px solid var(--rh-gray-200);
            padding: 20px 40px;
            position: sticky;
            top: 0;
            z-index: 100;
        }}
        
        .header-content {{
            max-width: 1200px;
            margin: 0 auto;
            display: flex;
            justify-content: space-between;
            align-items: center;
        }}
        
        .logo {{
            display: flex;
            align-items: center;
            gap: 12px;
            font-size: 1.5em;
            font-weight: 700;
            color: var(--rh-black);
        }}
        
        .logo-icon {{
            width: 40px;
            height: 40px;
            background: linear-gradient(135deg, #00C805 0%, #00A304 100%);
            border-radius: 12px;
            display: flex;
            align-items: center;
            justify-content: center;
            font-size: 1.3em;
        }}
        
        .header-right {{
            display: flex;
            align-items: center;
            gap: 20px;
        }}
        
        .btn-refresh {{
            background: var(--rh-black);
            color: var(--rh-white);
            border: none;
            padding: 10px 20px;
            border-radius: 24px;
            font-family: inherit;
            font-size: 14px;
            font-weight: 500;
            cursor: pointer;
            transition: all 0.2s;
        }}
        
        .btn-refresh:hover {{
            background: var(--rh-gray-700);
            transform: translateY(-1px);
        }}
        
        .last-updated {{
            color: var(--rh-gray-500);
            font-size: 13px;
        }}
        
        .container {{ max-width: 1200px; margin: 0 auto; padding: 30px 40px; }}
        
        .portfolio-hero {{
            text-align: center;
            padding: 40px 0;
            border-bottom: 1px solid var(--rh-gray-200);
            margin-bottom: 30px;
        }}
        
        .portfolio-label {{
            color: var(--rh-gray-500);
            font-size: 13px;
            font-weight: 500;
            text-transform: uppercase;
            letter-spacing: 0.5px;
            margin-bottom: 8px;
        }}
        
        .portfolio-value {{
            font-size: 4em;
            font-weight: 700;
            margin-bottom: 10px;
            letter-spacing: -1px;
        }}
        
        .portfolio-change {{
            font-size: 18px;
            font-weight: 500;
            display: flex;
            align-items: center;
            justify-content: center;
            gap: 8px;
        }}
        
        .change-positive {{ color: var(--rh-green); }}
        .change-negative {{ color: var(--rh-red); }}
        .change-arrow {{ font-size: 14px; }}
        
        .summary-grid {{
            display: grid;
            grid-template-columns: repeat(4, 1fr);
            gap: 16px;
            margin-bottom: 30px;
        }}
        
        .summary-card {{
            background: var(--rh-gray-100);
            border-radius: 16px;
            padding: 20px;
            transition: all 0.2s;
        }}
        
        .summary-card:hover {{
            background: var(--rh-gray-200);
        }}
        
        .summary-label {{
            color: var(--rh-gray-500);
            font-size: 13px;
            font-weight: 500;
            margin-bottom: 8px;
            text-transform: uppercase;
            letter-spacing: 0.5px;
        }}
        
        .summary-value {{
            font-size: 1.8em;
            font-weight: 700;
        }}
        
        .summary-value.win {{ color: var(--rh-green); }}
        .summary-value.loss {{ color: var(--rh-red); }}
        .summary-value.pending {{ color: var(--rh-blue); }}
        
        .section-title {{
            font-size: 24px;
            font-weight: 700;
            margin: 40px 0 20px;
            display: flex;
            align-items: center;
            gap: 10px;
        }}
        
        .section-count {{
            background: var(--rh-gray-200);
            color: var(--rh-gray-700);
            font-size: 14px;
            font-weight: 600;
            padding: 4px 12px;
            border-radius: 12px;
        }}
        
        .trades-grid {{
            display: grid;
            gap: 12px;
        }}
        
        .trade-card {{
            background: var(--rh-white);
            border: 1px solid var(--rh-gray-200);
            border-radius: 12px;
            padding: 16px 20px;
            display: flex;
            justify-content: space-between;
            align-items: center;
            transition: all 0.2s;
        }}
        
        .trade-card:hover {{
            border-color: var(--rh-gray-300);
            box-shadow: 0 2px 8px rgba(0,0,0,0.04);
        }}
        
        .trade-card.win {{
            background: var(--rh-green-light);
            border-color: var(--rh-green);
        }}
        
        .trade-card.loss {{
            background: var(--rh-red-light);
            border-color: var(--rh-red);
        }}
        
        .trade-left {{
            display: flex;
            flex-direction: column;
            gap: 4px;
        }}
        
        .trade-symbol {{
            font-size: 16px;
            font-weight: 600;
            color: var(--rh-black);
        }}
        
        .trade-meta {{
            font-size: 13px;
            color: var(--rh-gray-500);
        }}
        
        .trade-right {{
            text-align: right;
        }}
        
        .trade-pnl {{
            font-size: 18px;
            font-weight: 700;
        }}
        
        .trade-pnl.win {{ color: var(--rh-green); }}
        .trade-pnl.loss {{ color: var(--rh-red); }}
        .trade-pnl.pending {{ color: var(--rh-blue); }}
        
        .table-container {{
            background: var(--rh-white);
            border: 1px solid var(--rh-gray-200);
            border-radius: 16px;
            overflow: hidden;
        }}
        
        table {{
            width: 100%;
            border-collapse: collapse;
        }}
        
        thead {{
            background: var(--rh-gray-100);
        }}
        
        th {{
            padding: 14px 16px;
            text-align: left;
            font-size: 13px;
            font-weight: 600;
            color: var(--rh-gray-500);
            text-transform: uppercase;
            letter-spacing: 0.5px;
            border-bottom: 1px solid var(--rh-gray-200);
        }}
        
        td {{
            padding: 16px;
            font-size: 14px;
            border-bottom: 1px solid var(--rh-gray-200);
        }}
        
        tr:last-child td {{
            border-bottom: none;
        }}
        
        tr:hover td {{
            background: var(--rh-gray-100);
        }}
        
        .trade-id {{
            font-family: 'SF Mono', monospace;
            font-size: 11px;
            color: var(--rh-gray-500);
            background: var(--rh-gray-100);
            padding: 2px 6px;
            border-radius: 4px;
        }}
        
        .status {{
            display: inline-flex;
            align-items: center;
            gap: 6px;
            padding: 6px 12px;
            border-radius: 20px;
            font-size: 12px;
            font-weight: 600;
            text-transform: uppercase;
            letter-spacing: 0.3px;
        }}
        
        .status-win {{
            background: var(--rh-green-light);
            color: var(--rh-green);
        }}
        
        .status-loss {{
            background: var(--rh-red-light);
            color: var(--rh-red);
        }}
        
        .status-pending {{
            background: var(--rh-gray-200);
            color: var(--rh-gray-700);
        }}
        
        .status-dot {{
            width: 6px;
            height: 6px;
            border-radius: 50%;
        }}
        
        .status-win .status-dot {{ background: var(--rh-green); }}
        .status-loss .status-dot {{ background: var(--rh-red); }}
        .status-pending .status-dot {{ background: var(--rh-gray-500); }}
        
        @media (max-width: 768px) {{
            .summary-grid {{ grid-template-columns: repeat(2, 1fr); }}
            .portfolio-value {{ font-size: 2.5em; }}
            .header {{ padding: 16px 20px; }}
            .container {{ padding: 20px; }}
            .trade-card {{ flex-direction: column; align-items: flex-start; gap: 12px; }}
            .trade-right {{ text-align: left; width: 100%; }}
            table {{ font-size: 12px; }}
            th, td {{ padding: 10px 12px; }}
            .daily-header {{ flex-direction: column; align-items: flex-start; gap: 10px; }}
            .daily-right {{ text-align: left; width: 100%; }}
        }}
        
        /* Daily Summary Cards */
        .daily-grid {{
            display: grid;
            gap: 16px;
        }}
        
        .daily-summary {{
            background: var(--rh-white);
            border: 1px solid var(--rh-gray-200);
            border-radius: 16px;
            overflow: hidden;
            transition: all 0.2s;
        }}
        
        .daily-summary:hover {{
            box-shadow: 0 4px 12px rgba(0,0,0,0.08);
        }}
        
        .daily-summary.win {{
            border-color: var(--rh-green);
            background: linear-gradient(to bottom, var(--rh-green-light) 0%, var(--rh-white) 60px);
        }}
        
        .daily-summary.loss {{
            border-color: var(--rh-red);
            background: linear-gradient(to bottom, var(--rh-red-light) 0%, var(--rh-white) 60px);
        }}
        
        .daily-header {{
            display: flex;
            justify-content: space-between;
            align-items: center;
            padding: 20px;
            border-bottom: 1px solid var(--rh-gray-200);
        }}
        
        .daily-left {{
            display: flex;
            flex-direction: column;
            gap: 4px;
        }}
        
        .daily-date {{
            font-size: 18px;
            font-weight: 700;
            color: var(--rh-black);
        }}
        
        .daily-meta {{
            font-size: 13px;
            color: var(--rh-gray-500);
        }}
        
        .daily-right {{
            text-align: right;
        }}
        
        .daily-pnl {{
            font-size: 24px;
            font-weight: 700;
            margin-bottom: 6px;
        }}
        
        .daily-pnl.win {{ color: var(--rh-green); }}
        .daily-pnl.loss {{ color: var(--rh-red); }}
        
        .daily-trades {{
            padding: 12px 20px;
            background: var(--rh-gray-100);
        }}
        
        .nested-trade {{
            display: flex;
            justify-content: space-between;
            align-items: center;
            padding: 12px 16px;
            margin: 8px 0;
            background: var(--rh-white);
            border-radius: 10px;
            border: 1px solid var(--rh-gray-200);
        }}
        
        .nested-left {{
            display: flex;
            flex-direction: column;
            gap: 2px;
        }}
        
        .nested-symbol {{
            font-size: 14px;
            font-weight: 600;
            color: var(--rh-black);
        }}
        
        .nested-meta {{
            font-size: 12px;
            color: var(--rh-gray-500);
        }}
        
        .nested-pnl {{
            font-size: 15px;
            font-weight: 600;
        }}
        
        .nested-pnl.win {{ color: var(--rh-green); }}
        .nested-pnl.loss {{ color: var(--rh-red); }}
    </style>
</head>
<body>
    <header class="header">
        <div class="header-content">
            <div class="logo">
                <div class="logo-icon">🌤️</div>
                <span>Weather Trading</span>
            </div>
            <div class="header-right">
                <span class="last-updated">Updated {updated_time}</span>
                <button class="btn-refresh" onclick="window.location.reload()">↻ Refresh</button>
            </div>
        </div>
    </header>

    <div class="container">
        <div class="portfolio-hero">
            <div class="portfolio-label">Total P&L (Resolved)</div>
            <div class="portfolio-value {portfolio_change_class}">{portfolio_value}</div>
            <div class="portfolio-change {portfolio_change_class}">
                <span class="change-arrow">{'▲' if pnl_is_positive else '▼'}</span>
                <span>{return_pct:+.1f}% total return</span>
            </div>
        </div>

        <div class="summary-grid">
            <div class="summary-card">
                <div class="summary-label">Total Trades</div>
                <div class="summary-value">{stats['total_trades']}</div>
            </div>
            <div class="summary-card">
                <div class="summary-label">Total Exposure</div>
                <div class="summary-value">${stats['total_exposure']:,.0f}</div>
            </div>
            <div class="summary-card">
                <div class="summary-label">Win Rate</div>
                <div class="summary-value pending">{stats['win_rate']:.0f}%</div>
            </div>
            <div class="summary-card">
                <div class="summary-label">Pending Trades</div>
                <div class="summary-value">{stats['pending_count']}</div>
            </div>
        </div>

        <h2 class="section-title">
            ✅ Daily Results
            <span class="section-count">{stats['resolved_count']}</span>
        </h2>
        <div class="daily-grid">
            {daily_cards}
        </div>

        <h2 class="section-title">
            🟡 Pending Trades
            <span class="section-count">{stats['pending_count']}</span>
        </h2>
        <div class="trades-grid">
            {pending_cards}
        </div>

        <h2 class="section-title">📈 Complete Trade History</h2>
        <div class="table-container">
            <table>
                <thead>
                    <tr>
                        <th>Date</th>
                        <th>Trade ID</th>
                        <th>Side</th>
                        <th>Size</th>
                        <th>Shares</th>
                        <th>Exp. Profit</th>
                        <th>Status</th>
                        <th style="text-align: right;">P&L</th>
                    </tr>
                </thead>
                <tbody>
                    {table_rows}
                </tbody>
            </table>
        </div>

        <div style="text-align: center; margin-top: 40px; padding: 20px; color: var(--rh-gray-500); font-size: 12px; border-top: 1px solid var(--rh-gray-200);">
            Data Source: paper_trades_v3.jsonl • Generated: {generated_time}<br>
            Weather Trading Dashboard V4 • Robinhood Style • Flask Server
        </div>
    </div>
</body>
</html>'''
    
    return html

@app.route('/')
def dashboard():
    """Serve dashboard - regenerates fresh HTML on each request"""
    trades = load_trades()
    
    if not trades:
        return "No trades found in database.", 404
    
    stats = calculate_stats(trades)
    html = generate_html(trades, stats)
    
    return Response(html, mimetype='text/html')

def main():
    """Run the Flask server - supports auto-reload on file changes"""
    print("🌤️ Dashboard Server - Robinhood Style")
    print("=" * 50)
    print("Visit: http://localhost:5001")
    print("Or:    http://192.168.1.66:5001")
    print("=" * 50)
    print("Features:")
    print("  • Regenerates on every page load")
    print("  • Uses Robinhood green/red colors")
    print("  • DM Sans typography")
    print("  • Mobile responsive")
    print("=" * 50)
    print("Press Ctrl+C to stop")
    print("=" * 50)
    
    # Run with debug=False for production, enable for development
    # Disable auto-reloader to prevent duplicate processes
    app.run(host='0.0.0.0', port=5001, debug=True, use_reloader=False)

if __name__ == '__main__':
    main()
