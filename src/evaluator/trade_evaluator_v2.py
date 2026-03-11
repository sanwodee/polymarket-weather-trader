#!/usr/bin/env python3
"""
Trade Evaluator V2 - Fee-aware trading

Key changes:
1. Account for Polymarket's 2% taker fee
2. Calculate net expected value after fees
3. Adjust position sizing for fee impact
4. Support maker orders (0% fee, potential rebate)
"""
import json
import os
from datetime import datetime
from typing import Dict, List, Optional


class TradeEvaluatorV2:
    """
    Fee-aware trade evaluator
    """
    
    # Risk parameters
    MAX_POSITION_USD = 10000      # $10K per market
    MAX_BANKROLL_PCT = 0.05       # 5% of bankroll
    MAX_PORTFOLIO_EXPOSURE = 0.30  # 30% total
    KELLY_FRACTION = 0.25          # Conservative Kelly (1/4 full Kelly)
    MIN_EDGE_PCT = 0.07            # 7% minimum edge
    
    # Polymarket fees
    TAKER_FEE_BPS = 200            # 2% taker fee (as of 2025)
    MAKER_FEE_BPS = 0              # 0% maker fee (plus potential rebate)
    
    def __init__(self, bankroll: float = 100000.0, use_maker_orders: bool = False):
        """
        Args:
            bankroll: Total trading bankroll in USD
            use_maker_orders: If True, use maker orders (0% fee) instead of taker (2% fee)
        """
        self.bankroll = bankroll
        self.use_maker_orders = use_maker_orders
        self.fee_bps = self.MAKER_FEE_BPS if use_maker_orders else self.TAKER_FEE_BPS
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
    
    def calculate_fees(self, gross_position: float, is_maker: bool = None) -> Dict:
        """
        Calculate trading fees for a position
        
        Args:
            gross_position: Position size before fees
            is_maker: If True, use maker fee; if None, use evaluator default
        
        Returns:
            Dict with fee breakdown
        """
        if is_maker is None:
            is_maker = self.use_maker_orders
        
        fee_bps = self.MAKER_FEE_BPS if is_maker else self.TAKER_FEE_BPS
        fee_rate = fee_bps / 10000
        
        entry_fee = gross_position * fee_rate
        
        # Assume same fee on exit (unless held to resolution - 0% fee)
        # For now, assume we'll trade out (worst case)
        exit_fee = gross_position * fee_rate
        
        total_fees = entry_fee + exit_fee
        
        return {
            'entry_fee': entry_fee,
            'exit_fee': exit_fee,
            'total_fees': total_fees,
            'fee_rate': fee_rate,
            'fee_bps': fee_bps,
            'net_position': gross_position - total_fees,
            'is_maker': is_maker
        }
    
    def calculate_net_expected_value(self, prediction: Dict, gross_position: float) -> Dict:
        """
        Calculate expected value after accounting for fees
        
        Returns:
            Dict with EV breakdown
        """
        model_prob = prediction['prediction']['probability_yes']
        market_price = prediction['market_comparison']['market_price_yes']
        
        # Gross EV (before fees)
        if prediction['recommendation']['side'] == 'YES':
            # Win: position * (1/price) * payout - position
            # Simplified: (prob * payout) - investment
            gross_payout = gross_position / market_price if market_price > 0 else 0
            gross_ev = (model_prob * gross_payout) - gross_position
        else:  # NO side
            # Payout on NO is (1 - price)
            gross_payout = gross_position / (1 - market_price) if (1 - market_price) > 0 else 0
            gross_ev = ((1 - model_prob) * gross_payout) - gross_position
        
        # Subtract fees
        fees = self.calculate_fees(gross_position)
        net_ev = gross_ev - fees['total_fees']
        
        # Net edge
        net_edge_pct = net_ev / gross_position if gross_position > 0 else 0
        
        return {
            'gross_ev': gross_ev,
            'gross_ev_pct': gross_ev / gross_position if gross_position > 0 else 0,
            'total_fees': fees['total_fees'],
            'fee_pct': fees['total_fees'] / gross_position if gross_position > 0 else 0,
            'net_ev': net_ev,
            'net_ev_pct': net_edge_pct,
            'feasible': net_ev > 0,  # Only trade if net EV > 0
            'fees': fees
        }
    
    def evaluate(self, prediction: Dict) -> Dict:
        """
        Evaluate a prediction and determine if we should trade (fee-aware)
        """
        market_id = prediction.get('market_id')
        question = prediction.get('question', 'Unknown')
        
        # Extract data
        model_prob = prediction['prediction']['probability_yes']
        market_price = prediction['market_comparison']['market_price_yes']
        edge = prediction['market_comparison']['divergence']
        edge_pct = prediction['market_comparison']['edge_percent']
        kelly_raw = prediction['market_comparison']['kelly_fraction']
        
        side = prediction['recommendation']['side']
        confidence = prediction['recommendation']['confidence']
        
        # === GROSS EDGE CHECK ===
        if edge_pct < self.MIN_EDGE_PCT:
            return {
                'market_id': market_id,
                'decision': 'PASS',
                'reason': f'Insufficient gross edge ({edge_pct:.1%} < {self.MIN_EDGE_PCT:.0%} minimum)',
                'edge_pct': edge_pct,
                'status': 'rejected'
            }
        
        # === KELLY CALCULATION (GROSS) ===
        kelly_fractional = kelly_raw * self.KELLY_FRACTION
        gross_position_size = self.bankroll * kelly_fractional
        
        # === NET EV CALCULATION (FEE-AWARE) ===
        net_ev_result = self.calculate_net_expected_value(prediction, gross_position_size)
        
        # Check if net EV is positive after fees
        if not net_ev_result['feasible']:
            return {
                'market_id': market_id,
                'decision': 'PASS',
                'reason': f'Net EV negative after fees ({net_ev_result["net_ev_pct"]:.1%})',
                'gross_edge_pct': edge_pct,
                'net_edge_pct': net_ev_result['net_ev_pct'],
                'fees_pct': net_ev_result['fee_pct'],
                'status': 'rejected'
            }
        
        # Recalculate position size based on net EV
        # If fees eat too much, reduce position
        position_size = gross_position_size
        if net_ev_result['fee_pct'] > 0.03:  # If fees > 3%, reduce position
            position_size = gross_position_size * 0.8  # Reduce by 20%
            net_ev_result = self.calculate_net_expected_value(prediction, position_size)
        
        # === POSITION SIZE CONSTRAINTS ===
        constraints = []
        
        if position_size > self.MAX_POSITION_USD:
            position_size = self.MAX_POSITION_USD
            constraints.append(f'Max position ${self.MAX_POSITION_USD:,}')
        
        max_by_bankroll = self.bankroll * self.MAX_BANKROLL_PCT
        if position_size > max_by_bankroll:
            position_size = max_by_bankroll
            constraints.append(f'Max {self.MAX_BANKROLL_PCT:.0%} of bankroll')
        
        # Portfolio exposure
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
        
        # Recalculate final net EV with adjusted position
        final_net_ev = self.calculate_net_expected_value(prediction, position_size)
        
        # Calculate shares
        position_size = round(position_size, 2)
        share_price = market_price if side == 'YES' else (1 - market_price)
        shares = int(position_size / share_price) if share_price > 0 else 0
        
        # === DECISION ===
        if position_size >= 100 and final_net_ev['net_ev'] > 0:
            decision = 'EXECUTE'
            reason = f'Gross: {edge_pct:.1%} | Net: {final_net_ev["net_ev_pct"]:.1%} | Fees: { final_net_ev["fee_pct"]:.1%}'
        else:
            decision = 'PASS'
            if final_net_ev['net_ev'] <= 0:
                reason = f'Net EV too small after fees (${final_net_ev["net_ev"]:.0f})'
            else:
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
                'is_maker': self.use_maker_orders,
                'confidence': confidence
            },
            'risk_analysis': {
                'gross_edge_pct': edge_pct,
                'net_edge_pct': final_net_ev['net_ev_pct'],
                'gross_ev': final_net_ev['gross_ev'],
                'net_ev': final_net_ev['net_ev'],
                'fee_cost': final_net_ev['total_fees'],
                'fee_pct': final_net_ev['fee_pct'] * 100,
                'kelly_fractional': kelly_fractional,
                'portfolio_exposure_pre': current_exposure,
                'portfolio_exposure_post': current_exposure + position_size/self.bankroll,
                'constraints_applied': constraints
            },
            'status': 'approved' if decision == 'EXECUTE' else 'rejected',
            'evaluated_at': datetime.now().isoformat()
        }
    
    def execute_paper_trade(self, evaluation: Dict) -> Dict:
        """Execute a paper trade (simulated)"""
        if evaluation.get('decision') != 'EXECUTE':
            return evaluation
        
        rec = evaluation['recommendation']
        risk = evaluation['risk_analysis']
        
        paper_trade = {
            'market_id': evaluation['market_id'],
            'paper_trade_id': f"paper_{datetime.now().strftime('%Y%m%d%H%M%S')}",
            'side': rec['side'],
            'size_usd': rec['size_usd'],
            'shares': rec['shares'],
            'is_maker': rec.get('is_maker', False),
            'expected_gross_profit': risk['gross_ev'],
            'expected_net_profit': risk['net_ev'],
            'fee_cost': risk['fee_cost'],
            'fee_pct': risk['fee_pct'],
            'status': 'PAPER_FILLED',
            'timestamp': datetime.now().isoformat()
        }
        
        # Save to log
        log_file = 'data/positions/paper_trades_v2.jsonl'
        os.makedirs(os.path.dirname(log_file), exist_ok=True)
        with open(log_file, 'a') as f:
            f.write(json.dumps(paper_trade) + '\n')
        
        evaluation['paper_trade'] = paper_trade
        evaluation['status'] = 'paper_executed'
        return evaluation


def main():
    """Test the fee-aware evaluator"""
    
    # Test with different fee structures
    print("💰 Testing Fee-Aware Trade Evaluator V2")
    print("=" * 60)
    
    # Test prediction
    prediction = {
        'market_id': 'test',
        'question': 'Test market',
        'prediction': {'probability_yes': 0.45, 'confidence': 'medium'},
        'market_comparison': {
            'market_price_yes': 0.34,
            'divergence': 0.11,
            'edge_percent': 0.32,
            'kelly_fraction': 0.17
        },
        'recommendation': {'side': 'YES', 'confidence': 'medium'}
    }
    
    print("\n1. TAKER MODE (2% fee):")
    print("-" * 40)
    evaluator_taker = TradeEvaluatorV2(bankroll=100000.0, use_maker_orders=False)
    result = evaluator_taker.evaluate(prediction)
    print(f"  Decision: {result['decision']}")
    if result['decision'] == 'EXECUTE':
        print(f"  Gross EV: ${result['risk_analysis']['gross_ev']:,.0f}")
        print(f"  Fee cost: ${result['risk_analysis']['fee_cost']:,.0f} ({result['risk_analysis']['fee_pct']:.1f}%)")
        print(f"  Net EV: ${result['risk_analysis']['net_ev']:,.0f}")
        print(f"  Position: ${result['recommendation']['size_usd']:,.0f}")
    else:
        print(f"  Reason: {result['reason']}")
    
    print("\n2. MAKER MODE (0% fee):")
    print("-" * 40)
    evaluator_maker = TradeEvaluatorV2(bankroll=100000.0, use_maker_orders=True)
    result = evaluator_maker.evaluate(prediction)
    print(f"  Decision: {result['decision']}")
    if result['decision'] == 'EXECUTE':
        print(f"  Gross EV: ${result['risk_analysis']['gross_ev']:,.0f}")
        print(f"  Fee cost: ${result['risk_analysis']['fee_cost']:,.0f} ({result['risk_analysis']['fee_pct']:.1f}%)")
        print(f"  Net EV: ${result['risk_analysis']['net_ev']:,.0f}")
        print(f"  Position: ${result['recommendation']['size_usd']:,.0f}")
    else:
        print(f"  Reason: {result['reason']}")
    
    print("\n" + "=" * 60)
    print("Key insight: 2% fee reduced our net EV significantly!")
    print("Maker orders would save ${:.0f} in fees per trade.".format(
        result['risk_analysis']['fee_cost'] if result['decision'] == 'EXECUTE' else 0
    ))


if __name__ == "__main__":
    main()
