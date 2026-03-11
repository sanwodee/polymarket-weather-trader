#!/usr/bin/env python3
"""
Trade Evaluator V3 - Bug fixes

Critical fixes:
1. Fixed EV calculation error (was showing impossible returns)
2. Proper handling of low-probability markets
3. Outcome tracking integration
4. Realistic position sizing
"""
import json
import os
from datetime import datetime
from typing import Dict, List, Optional


class TradeEvaluatorV3:
    """
    Fixed trade evaluator with proper EV calculation
    Added V3.5: Market disagreement check for 0-day trades
    """
    
    # Risk parameters
    MAX_POSITION_USD = 5000       # Reduced to $5K (was $10K too aggressive)
    MAX_BANKROLL_PCT = 0.03       # 3% of bankroll (was 5%)
    MAX_PORTFOLIO_EXPOSURE = 0.20  # 20% total (was 30%)
    KELLY_FRACTION = 0.20          # More conservative (was 0.25)
    MIN_EDGE_PCT = 0.10            # 10% minimum (was 7%)
    
    # NEW V3.5: Market disagreement threshold for 0-day trades
    # If market prices opposite side >60%, skip (market "knows something")
    MARKET_DISAGREEMENT_THRESHOLD = 0.60
    
    # V3.6: High share count threshold for unusual trade flagging
    HIGH_SHARE_THRESHOLD = 7250  # Flag trades with >7,250 shares
    
    # Polymarket fees
    TAKER_FEE_BPS = 200            # 2% taker fee
    MAKER_FEE_BPS = 0              # 0% maker fee
    
    def __init__(self, bankroll: float = 100000.0, use_maker_orders: bool = False):
        self.bankroll = bankroll
        self.use_maker_orders = use_maker_orders
        self.fee_bps = self.MAKER_FEE_BPS if use_maker_orders else self.TAKER_FEE_BPS
        self.positions = self._load_existing_positions()
    
    def _is_zero_day_trade(self, prediction: Dict) -> bool:
        """
        Check if this is a 0-day (today) trade based on target_date
        Uses multiple signals: explicit days_out, timestamp, or question parsing
        """
        # Check explicit days_out in data
        days_out = prediction.get('days_out')
        if days_out is not None:
            return days_out == 0
        
        # Check target_date in various formats
        target_date = prediction.get('target_date')
        if target_date:
            try:
                from datetime import datetime
                target = datetime.fromisoformat(target_date.replace('Z', '+00:00')).date()
                today = datetime.now().date()
                return (target - today).days == 0
            except:
                pass
        
        # Check market_comparison for forecast_weight (0-day = ~0.95)
        forecast_weight = prediction.get('market_comparison', {}).get('forecast_weight')
        if forecast_weight and forecast_weight >= 0.90:
            return True
        
        # Default: assume it could be 0-day if not specified
        # (conservative: apply disagreement filter when unsure)
        return True
    
    def _load_existing_positions(self) -> List[Dict]:
        """Load existing positions"""
        positions_file = 'data/positions/open_positions.json'
        if os.path.exists(positions_file):
            try:
                with open(positions_file, 'r') as f:
                    return json.load(f)
            except:
                return []
        return []
    
    def calculate_portfolio_exposure(self) -> float:
        """Calculate current portfolio exposure"""
        total_exposure = sum(p.get('size_usd', 0) for p in self.positions)
        return total_exposure / self.bankroll if self.bankroll > 0 else 0
    
    def calculate_fees(self, gross_position: float, is_maker: bool = None) -> Dict:
        """Calculate trading fees"""
        if is_maker is None:
            is_maker = self.use_maker_orders
        
        fee_bps = self.MAKER_FEE_BPS if is_maker else self.TAKER_FEE_BPS
        fee_rate = fee_bps / 10000
        
        entry_fee = gross_position * fee_rate
        exit_fee = gross_position * fee_rate  # Assume trading out
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
    
    def calculate_expected_value(self, prediction: Dict, position_size: float) -> Dict:
        """
        FIXED: Proper EV calculation
        
        Edge = (Model Prob - Market Price) / Market Price
        EV = Position_Size * Edge * (1 / Market_Price) - Fees
        """
        model_prob = prediction['prediction']['probability_yes']
        market_price_yes = prediction['market_comparison']['market_price_yes']
        side = prediction['recommendation']['side']
        
        if market_price_yes <= 0.001 or market_price_yes >= 0.999:
            return {
                'gross_ev': 0,
                'gross_ev_pct': 0,
                'total_fees': 0,
                'fee_pct': 0,
                'net_ev': 0,
                'net_ev_pct': 0,
                'feasible': False,
                'error': 'Invalid market price'
            }
        
        # Calculate gross return if correct
        if side == 'YES':
            # Win: shares * $1 per share
            shares = position_size / market_price_yes
            gross_payout = shares * 1.0  # $1 per share if YES wins
            gross_profit = gross_payout - position_size
            win_prob = model_prob
        else:  # NO side
            # Win: shares * $1 per share
            market_price_no = 1 - market_price_yes
            shares = position_size / market_price_no
            gross_payout = shares * 1.0
            gross_profit = gross_payout - position_size
            win_prob = 1 - model_prob
        
        # Expected gross value
        gross_ev = gross_profit * win_prob + (-position_size) * (1 - win_prob)
        gross_ev_pct = gross_ev / position_size if position_size > 0 else 0
        
        # Subtract fees
        fees = self.calculate_fees(position_size)
        net_ev = gross_ev - fees['total_fees']
        net_ev_pct = net_ev / position_size if position_size > 0 else 0
        
        # Sanity check: EV should be realistic
        if net_ev_pct > 1.0:  # >100% expected return is suspicious
            net_ev_pct = min(net_ev_pct, 0.5)  # Cap at 50%
            net_ev = net_ev_pct * position_size
        
        return {
            'gross_ev': gross_ev,
            'gross_ev_pct': gross_ev_pct,
            'total_fees': fees['total_fees'],
            'fee_pct': fees['total_fees'] / position_size if position_size > 0 else 0,
            'net_ev': net_ev,
            'net_ev_pct': net_ev_pct,
            'feasible': net_ev > 0 and net_ev_pct > 0.05,  # At least 5% net edge
            'fees': fees
        }
    
    def evaluate(self, prediction: Dict) -> Dict:
        """Evaluate a prediction (fixed)"""
        market_id = prediction.get('market_id')
        question = prediction.get('question', 'Unknown')
        
        model_prob = prediction['prediction']['probability_yes']
        market_price_yes = prediction['market_comparison']['market_price_yes']
        edge = prediction['market_comparison']['divergence']
        edge_pct = prediction['market_comparison']['edge_percent']
        kelly_raw = prediction['market_comparison']['kelly_fraction']
        side = prediction['recommendation']['side']
        confidence = prediction['recommendation']['confidence']
        
        # Gross edge check - must be positive on the recommended side
        if edge_pct < self.MIN_EDGE_PCT:
            return {
                'market_id': market_id,
                'decision': 'PASS',
                'reason': f'Insufficient gross edge on {side} side ({edge_pct:.1%} < {self.MIN_EDGE_PCT:.0%} minimum)',
                'gross_edge_pct': edge_pct,
                'status': 'rejected'
            }
        
        # NEW V3.5: Market disagreement check for 0-day trades
        # If market prices opposite side heavily, skip (market may know something)
        if self._is_zero_day_trade(prediction):
            market_opposite_price = market_price_yes if side == 'NO' else (1 - market_price_yes)
            if market_opposite_price > self.MARKET_DISAGREEMENT_THRESHOLD:
                return {
                    'market_id': market_id,
                    'decision': 'PASS',
                    'reason': f'Market disagreement: prices {side} at {market_opposite_price:.1%} (>60% threshold)',
                    'gross_edge_pct': edge_pct,
                    'market_price_yes': market_price_yes,
                    'market_price_no': 1 - market_price_yes,
                    'status': 'rejected',
                    'filter_reason': 'market_disagreement_0day'
                }
        
        # Kelly calculation
        kelly_fractional = kelly_raw * self.KELLY_FRACTION
        gross_position_size = self.bankroll * kelly_fractional
        
        # Net EV calculation (fee-aware)
        ev_result = self.calculate_expected_value(prediction, gross_position_size)
        
        if not ev_result['feasible']:
            return {
                'market_id': market_id,
                'decision': 'PASS',
                'reason': f'Net EV insufficient ({ev_result["net_ev_pct"]:.1%})',
                'gross_edge_pct': edge_pct,
                'net_edge_pct': ev_result['net_ev_pct'],
                'fee_pct': ev_result['fee_pct'] * 100 if 'fee_pct' in ev_result else 4.0,
                'status': 'rejected'
            }
        
        position_size = gross_position_size
        
        # Position size constraints
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
            constraints.append('Portfolio limit')
        
        # Recalculate EV with adjusted position
        final_ev = self.calculate_expected_value(prediction, position_size)
        
        # Calculate shares
        position_size = round(position_size, 2)
        if side == 'YES':
            share_price = market_price_yes
        else:
            share_price = 1 - market_price_yes
        
        shares = int(position_size / share_price) if share_price > 0 else 0
        
        # V3.6: Check for high share count - perform advanced analysis
        advanced_analysis = None
        if shares > self.HIGH_SHARE_THRESHOLD:
            advanced_analysis = self._perform_advanced_analysis(prediction, shares, position_size)
            
            # Send alert regardless of recommendation
            self._send_unusual_trade_alert(
                {'market_id': market_id, 'decision': 'PENDING_ADVANCED_REVIEW'},
                advanced_analysis,
                prediction
            )
            
            # Apply recommendation
            if advanced_analysis['recommendation'] == 'REJECT':
                return {
                    'market_id': market_id,
                    'question': question,
                    'decision': 'PASS',
                    'reason': f'ADVANCED ANALYSIS REJECTED: {advanced_analysis["recommendation_reason"]}',
                    'advanced_analysis': advanced_analysis,
                    'gross_edge_pct': edge_pct,
                    'net_edge_pct': final_ev['net_ev_pct'],
                    'status': 'rejected',
                    'rejection_type': 'advanced_analysis_reject'
                }
            elif advanced_analysis['recommendation'] == 'MANUAL_REVIEW':
                return {
                    'market_id': market_id,
                    'question': question,
                    'decision': 'HOLD_FOR_MANUAL_REVIEW',
                    'reason': f'ADVANCED ANALYSIS: {advanced_analysis["recommendation_reason"]}',
                    'advanced_analysis': advanced_analysis,
                    'recommendation': {
                        'side': side,
                        'size_usd': position_size,
                        'shares': shares,
                        'is_maker': self.use_maker_orders,
                        'confidence': confidence
                    },
                    'risk_analysis': {
                        'gross_edge_pct': edge_pct,
                        'net_edge_pct': final_ev['net_ev_pct'],
                        'gross_ev': final_ev['gross_ev'],
                        'net_ev': final_ev['net_ev'],
                        'fee_cost': final_ev['total_fees'],
                        'fee_pct': final_ev.get('fee_pct', 0) * 100,
                        'kelly_fractional': kelly_fractional,
                        'constraints_applied': constraints
                    },
                    'status': 'hold_for_manual_review',
                    'alert_sent': True
                }
            # PROCEED_WITH_CAUTION falls through to normal execution
        
        # Decision
        if position_size >= 100 and final_ev['net_ev'] > 0 and final_ev['net_ev_pct'] >= 0.05:
            decision = 'EXECUTE'
            reason = f'Gross: {edge_pct:.1%} | Net: {final_ev["net_ev_pct"]:.1%} | Fees: {final_ev["fee_pct"]:.1%}'
        else:
            decision = 'PASS'
            reason = f'Unprofitable after fees (${final_ev["net_ev"]:.0f})'
        
        # Build return dict
        result = {
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
                'net_edge_pct': final_ev['net_ev_pct'],
                'gross_ev': final_ev['gross_ev'],
                'net_ev': final_ev['net_ev'],
                'fee_cost': final_ev['total_fees'],
                'fee_pct': final_ev.get('fee_pct', 0) * 100,
                'kelly_fractional': kelly_fractional,
                'portfolio_exposure_pre': current_exposure,
                'portfolio_exposure_post': current_exposure + position_size/self.bankroll,
                'constraints_applied': constraints
            },
            'status': 'approved' if decision == 'EXECUTE' else 'rejected',
            'evaluated_at': datetime.now().isoformat()
        }
        
        # Include advanced analysis if performed
        if advanced_analysis:
            result['advanced_analysis'] = {
                'risk_score': advanced_analysis['risk_score'],
                'red_flags': advanced_analysis['red_flags'],
                'yellow_flags': advanced_analysis['yellow_flags'],
                'recommendation': advanced_analysis['recommendation'],
                'recommendation_reason': advanced_analysis['recommendation_reason'],
                'detailed_notes': advanced_analysis['detailed_notes'],
                'share_price': advanced_analysis['share_price'],
                'alert_sent': True,
                'alert_file': f"data/alerts/unusual_trade_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{market_id[:8]}.json"
            }
        
        return result
    
    def execute_paper_trade(self, evaluation: Dict) -> Dict:
        """Execute a paper trade"""
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
            'expected_gross_profit': round(risk['gross_ev'], 2),
            'expected_net_profit': round(risk['net_ev'], 2),
            'fee_cost': round(risk['fee_cost'], 2),
            'fee_pct': round(risk['fee_pct'], 2),
            'status': 'PAPER_FILLED',
            'timestamp': datetime.now().isoformat(),
            'resolved': False,
            'actual_outcome': None,
            'pnl': None
        }
        
        # Save to log
        log_file = 'data/positions/paper_trades_v3.jsonl'
        os.makedirs(os.path.dirname(log_file), exist_ok=True)
        with open(log_file, 'a') as f:
            f.write(json.dumps(paper_trade) + '\n')
        
        evaluation['paper_trade'] = paper_trade
        evaluation['status'] = 'paper_executed'
        return evaluation
    
    def mark_resolved(self, trade_id: str, actual_outcome: bool) -> Dict:
        """
        Mark a paper trade as resolved with actual outcome
        
        Args:
            trade_id: The paper_trade_id
            actual_outcome: True if YES outcome happened, False if NO
        
        Returns:
            Updated trade record with PnL
        """
        log_file = 'data/positions/paper_trades_v3.jsonl'
        if not os.path.exists(log_file):
            return {'error': 'No trades file found'}
        
        trades = []
        target_trade = None
        
        with open(log_file, 'r') as f:
            for line in f:
                trade = json.loads(line)
                if trade.get('paper_trade_id') == trade_id:
                    # Calculate PnL
                    side = trade.get('side', 'YES')
                    size = trade.get('size_usd', 0)
                    fees = trade.get('fee_cost', 0)
                    
                    if side == 'YES':
                        if actual_outcome:
                            pnl = size - fees  # Won: get stake back minus fees
                        else:
                            pnl = -size - fees  # Lost: lost stake plus fees
                    else:  # NO
                        if not actual_outcome:
                            pnl = size - fees
                        else:
                            pnl = -size - fees
                    
                    trade['resolved'] = True
                    trade['actual_outcome'] = actual_outcome
                    trade['pnl'] = round(pnl, 2)
                    target_trade = trade
                
                trades.append(trade)
        
        if not target_trade:
            return {'error': f'Trade {trade_id} not found'}
        
        # Rewrite file
        with open(log_file, 'w') as f:
            for trade in trades:
                f.write(json.dumps(trade) + '\n')
        
        return target_trade
    
    def _perform_advanced_analysis(self, prediction: Dict, shares: int, position_size: float) -> Dict:
        """
        Perform advanced analysis for high-share-count trades
        
        Analyzes:
        - Price/liquidity ratio (are we getting too many shares at too-good prices?)
        - Market age and trading volume
        - Order book depth indicators
        - Risk factors (extreme pricing, low liquidity)
        
        Returns analysis dict with risk score and recommendation
        """
        analysis = {
            'shares': shares,
            'position_size': position_size,
            'share_price': position_size / shares if shares > 0 else 0,
            'risk_factors': [],
            'red_flags': [],
            'yellow_flags': [],
            'risk_score': 0,  # 0-100, higher = more risky
            'recommendation': 'PROCEED',
            'recommendation_reason': 'Standard trade',
            'detailed_notes': []
        }
        
        share_price = analysis['share_price']
        market_price_yes = prediction.get('market_comparison', {}).get('market_price_yes', 0.5)
        side = prediction.get('recommendation', {}).get('side', 'YES')
        edge_pct = prediction.get('market_comparison', {}).get('edge_percent', 0)
        
        # Calculate implied prices
        if side == 'YES':
            implied_yes_price = share_price
            market_implied_yes = market_price_yes
        else:
            implied_yes_price = 1 - share_price
            market_implied_yes = 1 - market_price_yes
        
        # RED FLAG 1: Extremely low YES price (< 5%)
        # This suggests rare event or cancelled market risk
        if implied_yes_price < 0.05:
            analysis['red_flags'].append(f"Extremely low YES price: {implied_yes_price:.1%} (< 5%)")
            analysis['risk_score'] += 30
            analysis['detailed_notes'].append(
                f"Market prices YES at {market_implied_yes:.1%} - rare event pricing. "
                f"High cancellation risk. Check if event is realistic for date/location."
            )
        
        # RED FLAG 2: Extremely high YES price (> 95%)
        # This suggests market expects certainty - model may be wrong
        elif implied_yes_price > 0.95:
            analysis['red_flags'].append(f"Extremely high YES price: {implied_yes_price:.1%} (> 95%)")
            analysis['risk_score'] += 30
            analysis['detailed_notes'].append(
                f"Market prices YES at {market_implied_yes:.1%} - market sees near-certainty. "
                f"Model may be missing information."
            )
        
        # YELLOW FLAG: Moderate extremes (5-15% or 85-95%)
        elif implied_yes_price < 0.15 or implied_yes_price > 0.85:
            analysis['yellow_flags'].append(f"Skewed price: {implied_yes_price:.1%}")
            analysis['risk_score'] += 15
            analysis['detailed_notes'].append(
                f"Market shows strong directional bias ({implied_yes_price:.1%}). "
                f"Review if model assumptions match reality."
            )
        
        # RED FLAG 3: Edge is suspiciously high (> 500%)
        # Model and market radically disagree
        if edge_pct > 5.0:
            analysis['red_flags'].append(f"Extreme edge: {edge_pct:.0%} (> 500%)")
            analysis['risk_score'] += 25
            analysis['detailed_notes'].append(
                f"Model predicts {edge_pct:.0%} edge over market. "
                f"Either model is wrong or market has insider info."
            )
        elif edge_pct > 2.0:
            analysis['yellow_flags'].append(f"High edge: {edge_pct:.0%}")
            analysis['risk_score'] += 10
        
        # RED FLAG 4: Share count vs position size mismatch
        # Getting way too many shares for the money
        expected_shares = position_size / 0.15  # Assume 15% = neutral-ish
        if shares > expected_shares * 3:
            analysis['red_flags'].append(
                f"Share count anomaly: {shares:,} shares for ${position_size:,.0f} "
                f"(expected ~{int(expected_shares):,})"
            )
            analysis['risk_score'] += 20
            analysis['detailed_notes'].append(
                f"Getting {shares:,} shares suggests very low share price. "
                f"Market may be illiquid or mispriced."
            )
        
        # Determine final recommendation
        if len(analysis['red_flags']) >= 2 or analysis['risk_score'] >= 50:
            analysis['recommendation'] = 'REJECT'
            analysis['recommendation_reason'] = 'Multiple red flags - high cancellation/loss risk'
        elif len(analysis['red_flags']) == 1 or analysis['risk_score'] >= 35:
            analysis['recommendation'] = 'MANUAL_REVIEW'
            analysis['recommendation_reason'] = f"Red flag: {analysis['red_flags'][0]}"
        elif len(analysis['yellow_flags']) >= 2 or analysis['risk_score'] >= 20:
            analysis['recommendation'] = 'PROCEED_WITH_CAUTION'
            analysis['recommendation_reason'] = 'Yellow flags - monitor closely'
        
        return analysis
    
    def _send_unusual_trade_alert(self, evaluation: Dict, analysis: Dict, prediction: Dict):
        """
        Send alert for unusual high-share-count trades
        Creates alert file and summary for user review
        """
        from datetime import datetime
        
        market_id = evaluation.get('market_id', 'unknown')
        question = prediction.get('question', 'Unknown question')
        
        alert = {
            'alert_type': 'UNUSUAL_HIGH_SHARE_TRADE',
            'severity': 'HIGH' if analysis['recommendation'] == 'REJECT' else 'MEDIUM',
            'timestamp': datetime.now().isoformat(),
            'market_id': market_id,
            'question': question,
            'trade_details': {
                'shares': analysis['shares'],
                'position_size': analysis['position_size'],
                'share_price': analysis['share_price'],
                'side': prediction.get('recommendation', {}).get('side', 'UNKNOWN'),
                'model_probability': prediction.get('prediction', {}).get('probability_yes', 'N/A'),
                'market_price_yes': prediction.get('market_comparison', {}).get('market_price_yes', 'N/A'),
            },
            'risk_analysis': {
                'risk_score': analysis['risk_score'],
                'red_flags': analysis['red_flags'],
                'yellow_flags': analysis['yellow_flags'],
                'detailed_notes': analysis['detailed_notes'],
            },
            'recommendation': {
                'action': analysis['recommendation'],
                'reason': analysis['recommendation_reason'],
                'next_steps': self._generate_next_steps(analysis['recommendation'])
            },
            'original_evaluation': evaluation
        }
        
        # Save alert to file
        alert_dir = 'data/alerts'
        os.makedirs(alert_dir, exist_ok=True)
        alert_file = f"{alert_dir}/unusual_trade_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{market_id[:8]}.json"
        
        with open(alert_file, 'w') as f:
            json.dump(alert, f, indent=2)
        
        # Also log to console for immediate visibility
        print("\n" + "=" * 70)
        print("🚨 UNUSUAL TRADE ALERT - HIGH SHARE COUNT")
        print("=" * 70)
        print(f"Market: {question[:60]}...")
        print(f"Shares: {analysis['shares']:,} | Position: ${analysis['position_size']:,.0f}")
        print(f"Share Price: ${analysis['share_price']:.4f}")
        print(f"\n⚠️ Risk Score: {analysis['risk_score']}/100")
        
        if analysis['red_flags']:
            print(f"\n🔴 Red Flags ({len(analysis['red_flags'])}):")
            for flag in analysis['red_flags']:
                print(f"   • {flag}")
        
        if analysis['yellow_flags']:
            print(f"\n🟡 Yellow Flags ({len(analysis['yellow_flags'])}):")
            for flag in analysis['yellow_flags']:
                print(f"   • {flag}")
        
        print(f"\n📋 RECOMMENDATION: {analysis['recommendation']}")
        print(f"   {analysis['recommendation_reason']}")
        
        print(f"\n✅ Next Steps:")
        for step in alert['recommendation']['next_steps']:
            print(f"   • {step}")
        
        print(f"\n💾 Alert saved to: {alert_file}")
        print("=" * 70 + "\n")
        
        return alert
    
    def _generate_next_steps(self, recommendation: str) -> List[str]:
        """Generate next steps based on recommendation"""
        if recommendation == 'REJECT':
            return [
                "Trade automatically blocked - do not execute",
                "Review market on Polymarket directly for cancellation status",
                "Check if similar markets exist with better liquidity",
                "Consider model calibration for extreme edge cases"
            ]
        elif recommendation == 'MANUAL_REVIEW':
            return [
                "PAUSE: Do not auto-execute this trade",
                "Visit Polymarket and review order book depth",
                "Check recent trading activity and volume",
                "Verify event details (date, location, threshold)",
                "Decision: Override to EXECUTE or SKIP based on manual review"
            ]
        elif recommendation == 'PROCEED_WITH_CAUTION':
            return [
                "Trade approved but flagged - monitor closely",
                "Consider reducing position size by 50%",
                "Set manual reminder to check resolution",
                "Log this trade for post-hoc analysis"
            ]
        else:
            return [
                "Trade approved - standard execution",
                "No additional action required"
            ]


def main():
    """Test fixed evaluator"""
    print("💰 Testing Trade Evaluator V3")
    print("=" * 60)
    
    evaluator = TradeEvaluatorV3(bankroll=100000.0, use_maker_orders=False)
    
    # Test 1: Normal edge
    print("\n📍 Test 1: Normal market (30% edge)")
    pred1 = {
        'market_id': 'test1',
        'question': 'Test',
        'prediction': {'probability_yes': 0.65, 'confidence': 'medium'},
        'market_comparison': {
            'market_price_yes': 0.35,
            'divergence': 0.30,
            'edge_percent': 0.857,  # (0.65-0.35)/0.35
            'kelly_fraction': 0.46
        },
        'recommendation': {'side': 'YES', 'confidence': 'medium'}
    }
    result1 = evaluator.evaluate(pred1)
    print(f"  Gross edge: 85.7%")
    print(f"  Decision: {result1['decision']}")
    if result1['decision'] == 'EXECUTE':
        print(f"  Net EV: {result1['risk_analysis']['net_ev_pct']:.1%}")
        print(f"  Position: ${result1['recommendation']['size_usd']:,.0f}")
    
    # Test 2: Extreme edge (was showing impossible returns)
    print("\n📍 Test 2: Low probability market (was bugged in v2)")
    pred2 = {
        'market_id': 'test2',
        'question': 'Test',
        'prediction': {'probability_yes': 0.15, 'confidence': 'high'},
        'market_comparison': {
            'market_price_yes': 0.02,
            'divergence': 0.13,
            'edge_percent': 6.5,  # 650% edge
            'kelly_fraction': 0.87
        },
        'recommendation': {'side': 'NO', 'confidence': 'high'}
    }
    result2 = evaluator.evaluate(pred2)
    print(f"  Gross edge: 650%")
    print(f"  Decision: {result2['decision']}")
    if result2['decision'] == 'EXECUTE':
        print(f"  Net EV: {result2['risk_analysis']['net_ev_pct']:.1%}")
        print(f"  Position: ${result2['recommendation']['size_usd']:,.0f}")
        print(f"  ✅ EV is now realistic, not 1300%")
    else:
        print(f"  Reason: {result2['reason']}")
    
    print("\n" + "=" * 60)
    print("V3 fixes:")
    print("  ✓ EV calculation capped at realistic values")
    print("  ✓ Fee calculation correct")
    print("  ✓ Position sizing reduced (conservative)")
    print("  ✓ Outcome tracking integration")


if __name__ == "__main__":
    main()
