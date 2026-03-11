#!/usr/bin/env python3
"""
Trade Evaluator - Edge calculation and Kelly criterion position sizing
"""
import json
import os
from datetime import datetime
from typing import Dict, List, Optional

class TradeEvaluator:
    """Evaluates trading opportunities and calculates optimal position sizing"""
    
    # Risk parameters
    MAX_POSITION_USD = 10000      # $10K per market
    MAX_BANKROLL_PCT = 0.05       # 5% of bankroll
    MAX_PORTFOLIO_EXPOSURE = 0.30  # 30% total
    KELLY_FRACTION = 0.25          # Conservative Kelly (1/4 full Kelly)
    MIN_EDGE_PCT = 0.07            # 7% minimum edge
    
    def __init__(self, bankroll: float = 100000.0):
        self.bankroll = bankroll
        self.positions = self._load_existing_positions()
    
    def _load_existing_positions(self) -> List[Dict]:
        """Load existing positions to calculate exposure"""
        positions_file = 'data/positions/open_positions.json'
        if os.path.exists(positions_file):
            try:
                with open(positions_file, 'r') as f:
                    return json.load(f)
            except:
                return []
        return []
    
    def calculate_portfolio_exposure(self) -> float:
        """Calculate current portfolio exposure (0-1)"""
        total_exposure = sum(p.get('size_usd', 0) for p in self.positions)
        return total_exposure / self.bankroll if self.bankroll > 0 else 0
    
    def evaluate(self, prediction: Dict) -> Dict:
        """Evaluate a prediction and determine if we should trade"""
        market_id = prediction.get('market_id')
        question = prediction.get('question', 'Unknown')
        
        model_prob = prediction['prediction']['probability_yes']
        market_price = prediction['market_comparison']['market_price_yes']
        edge = prediction['market_comparison']['divergence']
        edge_pct = prediction['market_comparison']['edge_percent']
        kelly_raw = prediction['market_comparison']['kelly_fraction']
        side = prediction['recommendation']['side']
        confidence = prediction['recommendation']['confidence']
        
        # Edge check
        if edge_pct < self.MIN_EDGE_PCT:
            return {
                'market_id': market_id,
                'decision': 'PASS',
                'reason': f'Insufficient edge ({edge_pct:.1%} < {self.MIN_EDGE_PCT:.0%} minimum)',
                'edge_pct': edge_pct,
                'status': 'rejected'
            }
        
        # Kelly calculation
        kelly_fractional = kelly_raw * self.KELLY_FRACTION
        position_size = self.bankroll * kelly_fractional
        
        # Position size constraints
        constraints = []
        
        if position_size > self.MAX_POSITION_USD:
            position_size = self.MAX_POSITION_USD
            constraints.append(f'Max position ${self.MAX_POSITION_USD:,}')
        
        max_by_bankroll = self.bankroll * self.MAX_BANKROLL_PCT
        if position_size > max_by_bankroll:
            position_size = max_by_bankroll
            constraints.append(f'Max {self.MAX_BANKROLL_PCT:.0%} of bankroll')
        
        # Portfolio exposure check
        current_exposure = self.calculate_portfolio_exposure()
        remaining_exposure = (self.MAX_PORTFOLIO_EXPOSURE - current_exposure) * self.bankroll
        
        if remaining_exposure <= 0:
            return {
                'market_id': market_id,
                'decision': 'PASS',
                'reason': f'Portfolio at max exposure ({current_exposure:.1%})',
                'status': 'rejected'
            }
        
        if position_size > remaining_exposure:
            position_size = remaining_exposure
            constraints.append(f'Remaining portfolio capacity')
        
        # Round and calculate shares
        position_size = round(position_size, 2)
        share_price = market_price if side == 'YES' else (1 - market_price)
        shares = int(position_size / share_price) if share_price > 0 else 0
        
        # Decision
        if position_size >= 100:
            decision = 'EXECUTE'
            reason = f'{edge_pct:.1%} edge, Kelly {kelly_fractional:.2%}, within limits'
        else:
            decision = 'PASS'
            reason = f'Position size too small (${position_size:.0f})'
        
        return {
            'market_id': market_id,
            'question': question,
            'decision': decision,
            'reason': reason,
            'recommendation': {
                'side': side,
                'size_usd': position_size,
                'shares': shares,
                'confidence': confidence
            },
            'risk_analysis': {
                'edge_pct': edge_pct,
                'kelly_fractional': kelly_fractional,
                'portfolio_exposure_pre': current_exposure,
                'portfolio_exposure_post': current_exposure + position_size/self.bankroll
            },
            'status': 'approved' if decision == 'EXECUTE' else 'rejected',
            'evaluated_at': datetime.now().isoformat()
        }
    
    def execute_paper_trade(self, evaluation: Dict) -> Dict:
        """Execute a paper trade (simulated)"""
        if evaluation.get('decision') != 'EXECUTE':
            return evaluation
        
        rec = evaluation['recommendation']
        paper_trade = {
            'market_id': evaluation['market_id'],
            'paper_trade_id': f"paper_{datetime.now().strftime('%Y%m%d%H%M%S')}",
            'side': rec['side'],
            'size_usd': rec['size_usd'],
            'shares': rec['shares'],
            'status': 'PAPER_FILLED',
            'timestamp': datetime.now().isoformat()
        }
        
        # Save to log
        log_file = 'data/positions/paper_trades.jsonl'
        os.makedirs(os.path.dirname(log_file), exist_ok=True)
        with open(log_file, 'a') as f:
            f.write(json.dumps(paper_trade) + '\n')
        
        evaluation['paper_trade'] = paper_trade
        evaluation['status'] = 'paper_executed'
        return evaluation


if __name__ == "__main__":
    evaluator = TradeEvaluator(bankroll=100000.0)
    
    # Test evaluation
    prediction = {
        'market_id': 'test',
        'question': 'Test market',
        'prediction': {'probability_yes': 0.45},
        'market_comparison': {
            'market_price_yes': 0.34,
            'divergence': 0.11,
            'edge_percent': 0.32,
            'kelly_fraction': 0.17
        },
        'recommendation': {'side': 'YES', 'confidence': 'high'}
    }
    
    result = evaluator.evaluate(prediction)
    print(f"Decision: {result['decision']}")
    if result['decision'] == 'EXECUTE':
        result = evaluator.execute_paper_trade(result)
        print(f"Paper trade ID: {result['paper_trade']['paper_trade_id']}")
    print(f"Reason: {result['reason']}")
