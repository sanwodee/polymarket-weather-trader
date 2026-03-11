#!/usr/bin/env python3
"""
Trade Evaluator V3 Test Mode - Less conservative for testing
"""
import json
import os
from datetime import datetime
from typing import Dict, List, Optional


class TradeEvaluatorV3Test:
    """
    V3 Test Mode - relaxed constraints for validation
    """
    
    # Relaxed parameters for testing
    MAX_POSITION_USD = 100          # $100 max per trade for testing
    MAX_BANKROLL_PCT = 0.10         # 10% of bankroll
    MAX_PORTFOLIO_EXPOSURE = 0.50   # 50% total
    KELLY_FRACTION = 0.50           # 50% Kelly
    MIN_EDGE_PCT = 0.05             # 5% minimum (relaxed from 10%)
    
    # Polymarket fees
    TAKER_FEE_BPS = 200
    MAKER_FEE_BPS = 0
    
    def __init__(self, bankroll: float = 1000.0, use_maker_orders: bool = False):
        self.bankroll = bankroll
        self.use_maker_orders = use_maker_orders
        self.fee_bps = self.MAKER_FEE_BPS if use_maker_orders else self.TAKER_FEE_BPS
        self.positions = []
    
    def calculate_portfolio_exposure(self) -> float:
        total_exposure = sum(p.get('size_usd', 0) for p in self.positions)
        return total_exposure / self.bankroll if self.bankroll > 0 else 0
    
    def calculate_fees(self, gross_position: float, is_maker: bool = None) -> Dict:
        fee_rate = self.fee_bps / 10000
        entry_fee = gross_position * fee_rate
        exit_fee = gross_position * fee_rate
        total_fees = entry_fee + exit_fee
        
        return {
            'entry_fee': entry_fee,
            'exit_fee': exit_fee,
            'total_fees': total_fees,
            'fee_rate': fee_rate,
            'net_position': gross_position - total_fees
        }
    
    def calculate_expected_value(self, prediction: Dict, position_size: float) -> Dict:
        model_prob = prediction['prediction']['probability_yes']
        market_price_yes = prediction['market_comparison']['market_price_yes']
        side = prediction['recommendation']['side']
        
        if market_price_yes <= 0.001 or market_price_yes >= 0.999:
            return {'feasible': False, 'net_ev': 0, 'net_ev_pct': 0}
        
        # Calculate return
        if side == 'YES':
            shares = position_size / market_price_yes if market_price_yes > 0 else 0
            gross_payout = shares * 1.0
            gross_profit = gross_payout - position_size
            win_prob = model_prob
        else:
            market_price_no = 1 - market_price_yes
            shares = position_size / market_price_no if market_price_no > 0 else 0
            gross_payout = shares * 1.0
            gross_profit = gross_payout - position_size
            win_prob = 1 - model_prob
        
        gross_ev = gross_profit * win_prob - position_size * (1 - win_prob)
        gross_ev_pct = gross_ev / position_size if position_size > 0 else 0
        
        fees = self.calculate_fees(position_size)
        net_ev = gross_ev - fees['total_fees']
        net_ev_pct = net_ev / position_size if position_size > 0 else 0
        
        return {
            'gross_ev': gross_ev,
            'gross_ev_pct': gross_ev_pct,
            'total_fees': fees['total_fees'],
            'fee_pct': fees['total_fees'] / position_size if position_size > 0 else 0,
            'net_ev': net_ev,
            'net_ev_pct': net_ev_pct,
            'feasible': net_ev > 0
        }
    
    def evaluate(self, prediction: Dict) -> Dict:
        market_id = prediction.get('market_id')
        question = prediction.get('question', 'Unknown')
        
        model_prob = prediction['prediction']['probability_yes']
        market_price_yes = prediction['market_comparison']['market_price_yes']
        edge = prediction['market_comparison']['divergence']
        edge_pct = prediction['market_comparison']['edge_percent']
        kelly_raw = prediction['market_comparison']['kelly_fraction']
        side = prediction['recommendation']['side']
        confidence = prediction['recommendation']['confidence']
        
        # Relaxed edge check
        if abs(edge_pct) < self.MIN_EDGE_PCT:
            return {
                'market_id': market_id,
                'decision': 'PASS',
                'reason': f'Insufficient edge ({edge_pct:.1%} < {self.MIN_EDGE_PCT:.0%})',
                'status': 'rejected'
            }
        
        # Kelly calculation
        kelly_fractional = kelly_raw * self.KELLY_FRACTION
        gross_position = self.bankroll * kelly_fractional
        
        # EV calculation
        ev = self.calculate_expected_value(prediction, gross_position)
        
        if not ev['feasible']:
            return {
                'market_id': market_id,
                'decision': 'PASS',
                'reason': f'Unprofitable after fees ({ev["net_ev_pct"]:.1%})',
                'status': 'rejected'
            }
        
        # Size constraints
        position_size = min(gross_position, self.MAX_POSITION_USD, 
                          self.bankroll * self.MAX_BANKROLL_PCT)
        
        remaining = (self.MAX_PORTFOLIO_EXPOSURE - self.calculate_portfolio_exposure()) * self.bankroll
        if position_size > remaining:
            position_size = remaining
        
        position_size = round(max(10, position_size), 2)  # Min $10
        
        # Shares
        if side == 'YES':
            share_price = market_price_yes
        else:
            share_price = 1 - market_price_yes
        shares = int(position_size / share_price) if share_price > 0 else 0
        
        # Recalculate EV with adjusted size
        final_ev = self.calculate_expected_value(prediction, position_size)
        
        return {
            'market_id': market_id,
            'question': question,
            'decision': 'EXECUTE',
            'reason': f"Edge: {edge_pct:.1%} | Net: {final_ev['net_ev_pct']:.1%}",
            'recommendation': {
                'side': side,
                'size_usd': position_size,
                'shares': shares,
                'confidence': confidence
            },
            'risk_analysis': {
                'gross_edge_pct': edge_pct,
                'net_edge_pct': final_ev['net_ev_pct'],
                'net_ev': final_ev['net_ev'],
                'fee_cost': final_ev['total_fees']
            },
            'status': 'approved',
            'evaluated_at': datetime.now().isoformat()
        }
    
    def execute_paper_trade(self, evaluation: Dict) -> Dict:
        if evaluation.get('decision') != 'EXECUTE':
            return evaluation
        
        rec = evaluation['recommendation']
        risk = evaluation['risk_analysis']
        
        paper_trade = {
            'market_id': evaluation['market_id'],
            'paper_trade_id': f"test_{datetime.now().strftime('%Y%m%d%H%M%S')}",
            'side': rec['side'],
            'size_usd': rec['size_usd'],
            'shares': rec['shares'],
            'expected_net_profit': round(risk['net_ev'], 2),
            'status': 'PAPER_FILLED',
            'timestamp': datetime.now().isoformat(),
            'resolved': False
        }
        
        log_file = 'data/positions/test_trades.jsonl'
        os.makedirs(os.path.dirname(log_file), exist_ok=True)
        with open(log_file, 'a') as f:
            f.write(json.dumps(paper_trade) + '\n')
        
        evaluation['paper_trade'] = paper_trade
        return evaluation
