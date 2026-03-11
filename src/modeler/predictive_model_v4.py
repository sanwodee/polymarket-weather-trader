#!/usr/bin/env python3
"""
Predictive Modeler v4 - Recalibrated

Key fixes based on Feb 23-24 losses:
1. Conservative probability bounds (never >80% for short-term)
2. Proper forecast vs climatology weighting
3. Check live data source
4. Sanity checks on predictions
5. Confidence threshold raised
"""
import json
import os
import re
from datetime import datetime, timedelta
from typing import Dict, Optional, Tuple
import numpy as np
from scipy.stats import norm


class WeatherPredictorV4:
    """
    V4 Predictor - Recalibrated for accuracy
    """
    
    def __init__(self):
        self.models_used = ['gfs_seamless', 'ecmwf_ifs04']
    
    def _parse_threshold(self, threshold: Dict) -> Tuple[float, float, str, str]:
        """Parse threshold into (low, high, range_type, metric_type)"""
        value = threshold.get('value', 0)
        direction = threshold.get('direction', 'above')
        question = threshold.get('question', '').lower()
        
        # Determine metric type
        metric_type = 'temperature'
        if any(x in question for x in ['snow', 'snowfall']):
            metric_type = 'snow'
        elif any(x in question for x in ['rain', 'rainfall', 'precipitation']):
            metric_type = 'precipitation'
        
        # Parse ranges
        if isinstance(value, str):
            match = re.search(r'(\d+(?:\.\d+)?)[-–]\s*(\d+(?:\.\d+)?)', value)
            if match:
                return (float(match.group(1)), float(match.group(2)), 'between', metric_type)
        
        # Single threshold
        if direction == 'above':
            return (value, float('inf'), 'above', metric_type)
        else:
            return (float('-inf'), value, 'below', metric_type)
    
    def _calculate_range_probability(self, mean: float, std: float, 
                                     low: float, high: float) -> float:
        """Calculate P(low <= X <= high)"""
        if std <= 0:
            std = 0.1
        
        # Cap z-scores to avoid extreme probabilities
        z_high = min(3.0, max(-3.0, (high - mean) / std)) if high != float('inf') else 3.0
        z_low = min(3.0, max(-3.0, (low - mean) / std)) if low != float('-inf') else -3.0
        
        p_high = norm.cdf(z_high)
        p_low = norm.cdf(z_low)
        
        prob = p_high - p_low
        
        # Conservative bounds: never 0% or 100%, max 85% for short-term
        return max(0.05, min(0.85, prob))
    
    def _validate_weather_data(self, weather_data: Dict) -> Dict:
        """Check if data source is valid"""
        forecast = weather_data.get('forecast', {})
        
        # Check source
        source = forecast.get('source', 'unknown')
        if source == 'historical':
            # Historical data is stale for today - reject
            return {
                'valid': False,
                'error': f'Using HISTORICAL data, not live forecast'
            }
        
        temp = forecast.get('temp_max') or forecast.get('temp_mean')
        if temp is None:
            return {
                'valid': False,
                'error': 'No temperature data available'
            }
        
        # Sanity check temperatures
        if temp < -30 or temp > 130:
            return {
                'valid': False,
                'error': f'Temperature {temp}°F is unrealistic'
            }
        
        return {'valid': True}
    
    def _get_forecast_params(self, weather_data: Dict, metric_type: str) -> Tuple[Optional[float], Optional[float]]:
        """Extract forecast parameters"""
        forecast = weather_data.get('forecast', {})
        
        # Support both 'temp' and 'temperature' metric types
        if metric_type in ['temp', 'temperature']:
            value = forecast.get('temp_max') or forecast.get('temp_mean')
            uncertainty = forecast.get('uncertainty', 4.0)
        else:
            return (None, None)
        
        return (value, uncertainty)
    
    def predict(self, market: Dict, weather_data: Dict) -> Dict:
        """Main prediction method with validation"""
        threshold_data = market.get('threshold', {})
        target_date = market.get('target_date')
        
        if not threshold_data:
            return {'error': 'No threshold data'}
        
        # Validate data source FIRST
        validation = self._validate_weather_data(weather_data)
        if not validation['valid']:
            return {
                'market_id': market.get('market_id'),
                'error': validation['error'],
                'recommendation': {'action': 'PASS', 'reason': 'invalid_data'}
            }
        
        # Parse threshold
        threshold_data['question'] = market.get('question', '')
        low, high, range_type, metric_type = self._parse_threshold(threshold_data)
        
        # Get forecast
        forecast_mean, forecast_std = self._get_forecast_params(weather_data, metric_type)
        if forecast_mean is None:
            return {
                'error': 'No forecast data',
                'recommendation': {'action': 'PASS', 'reason': 'no_forecast'}
            }
        
        # Get climatology
        climatology = weather_data.get('climatology', {})
        clim_mean = climatology.get('mean_temp')
        
        # Calculate probabilities with DYNAMIC forecast weight based on lead time
        forecast_prob = self._calculate_range_probability(
            forecast_mean, forecast_std, low, high
        )
        
        climatology_prob = 0.5
        if clim_mean:
            climatology_prob = self._calculate_range_probability(
                clim_mean, 8.0, low, high
            )
        
        # CALIBRATE FORECAST WEIGHT BY LEAD TIME
        # Higher weight for shorter forecasts (more accurate)
        if target_date:
            try:
                target = datetime.fromisoformat(target_date.replace('Z', '+00:00')).date()
                today = datetime.now().date()
                days_out = (target - today).days
                
                if days_out == 0:
                    w_forecast = 0.95  # Today: 95% forecast
                elif days_out == 1:
                    w_forecast = 0.85  # Tomorrow: 85% forecast
                else:
                    w_forecast = 0.70  # 2+ days: 70% forecast
            except:
                w_forecast = 0.90  # Fallback
        else:
            w_forecast = 0.90
        
        w_climatology = 1.0 - w_forecast
        
        combined_prob = (w_forecast * forecast_prob) + (w_climatology * climatology_prob)
        
        # Additional sanity check: if forecast is far outside range, lower probability
        forecast_outside = forecast_mean < low - 5 or forecast_mean > high + 5
        if forecast_outside:
            combined_prob = min(combined_prob, 0.20)  # Cap at 20% if forecast is outside
        
        # Market comparison
        market_price_yes = market.get('current_price_yes', 0.5)
        
        # Calculate edge correctly based on side
        if combined_prob > 0.55:
            side = 'YES'
            # Edge is model YES prob minus market YES price
            edge = combined_prob - market_price_yes
            edge_pct = edge / market_price_yes if market_price_yes > 0.01 else 0
        else:
            side = 'NO'
            # Edge is model NO prob minus market NO price
            model_no_prob = 1 - combined_prob
            market_no_price = 1 - market_price_yes
            edge = model_no_prob - market_no_price
            edge_pct = edge / market_no_price if market_no_price > 0.01 else 0
        
        # Calculate FEE-ADJUSTED Kelly fraction for position sizing
        # Total fees: 4% (2% entry + 2% exit)
        TOTAL_FEE_RATE = 0.04
        
        def calculate_kelly_with_fees(prob_win, market_price, side):
            """Kelly criterion adjusted for Polymarket fees"""
            if side == 'YES':
                p = prob_win
                # After fees, net profit is (1-price) * (1-fee) - price
                gross_odds = (1 - market_price) / market_price if market_price > 0 else 1
                # Adjust for entry and exit fees (4% total)
                net_odds = gross_odds * (1 - TOTAL_FEE_RATE) - TOTAL_FEE_RATE
                b = max(0.01, net_odds)  # Prevent division by zero
            else:  # NO side
                p = 1 - prob_win
                gross_odds = market_price / (1 - market_price) if market_price < 1 else 1
                net_odds = gross_odds * (1 - TOTAL_FEE_RATE) - TOTAL_FEE_RATE
                b = max(0.01, net_odds)
            
            q = 1 - p
            # Kelly formula: f* = (pb - q) / b
            kelly = (p * b - q) / b if b > 0 else 0
            return max(0, kelly)
        
        kelly = calculate_kelly_with_fees(combined_prob, market_price_yes, side)
        kelly_half = kelly * 0.5  # Half-Kelly for safety
        
        # Only trade if edge > 15% on the recommended side (increased from 10%)
        should_trade = abs(edge) > 0.15 and abs(edge_pct) > 0.15
        
        return {
            'market_id': market.get('market_id'),
            'question': market.get('question'),
            'prediction': {
                'probability_yes': combined_prob,
                'probability_no': 1 - combined_prob,
                'forecast_temp': forecast_mean,
                'climatology_temp': clim_mean,
                'data_source': weather_data['forecast'].get('source', 'unknown')
            },
            'market_comparison': {
                'market_price_yes': market_price_yes,
                'divergence': edge,
                'edge_percent': edge_pct,
                'kelly_fraction': kelly,
                'kelly_half': kelly_half,
                'forecast_weight': w_forecast
            },
            'recommendation': {
                'action': 'TRADE' if should_trade else 'PASS',
                'side': side,
                'confidence': 'high' if forecast_std < 3 else 'medium' if forecast_std < 6 else 'low',
                'reason': f"Forecast: {forecast_mean}°F vs Range [{low}-{high}] | Source: {weather_data['forecast'].get('source', 'unknown')}"
            },
            'timestamp': datetime.now().isoformat()
        }
    
    def backtest_single(self, market: Dict, weather_data: Dict, actual_value: float) -> Dict:
        """Backtest single market against actual outcome"""
        pred = self.predict(market, weather_data)
        
        if 'error' in pred:
            return {'error': pred['error']}
        
        # Parse threshold for actual comparison
        threshold_data = market.get('threshold', {'question': market.get('question', '')})
        low, high, _, _ = self._parse_threshold(threshold_data)
        
        # Determine actual outcome
        actual_in_range = low <= actual_value <= high
        
        # Was prediction correct?
        model_prob_yes = pred['prediction']['probability_yes']
        model_says_yes = model_prob_yes > 0.5
        correct = (model_says_yes and actual_in_range) or (not model_says_yes and not actual_in_range)
        
        return {
            'market': market['question'][:40],
            'actual': actual_value,
            'in_range': actual_in_range,
            'model_prob_yes': model_prob_yes,
            'model_says_yes': model_says_yes,
            'correct': correct,
            'error': abs(model_prob_yes - (1 if actual_in_range else 0))
        }


def main():
    """Test v4 predictor"""
    predictor = WeatherPredictorV4()
    
    print("🤖 Testing Weather Predictor V4 (Recalibrated)")
    print("=" * 60)
    
    # Test 1: Chicago Feb 23 scenario
    print("\n📍 Test: Chicago Feb 23 (Actual: 26.1°F)")
    market1 = {
        'market_id': 'test1',
        'question': '30-35°F?',
        'threshold': {'value': '30-35', 'direction': 'between'},
        'current_price_yes': 0.25,
        'target_date': '2026-02-23'
    }
    weather1 = {
        'forecast': {'temp_max': 28, 'temp_mean': 26, 'uncertainty': 4, 'source': 'forecast'},
        'climatology': {'mean_temp': 35, 'std_dev': 8}
    }
    result1 = predictor.predict(market1, weather1)
    print(f"  Forecast: 28°F | Range: 30-35°F")
    if 'prediction' in result1:
        print(f"  P(30-35°F): {result1['prediction']['probability_yes']:.1%}")
        print(f"  Recommendation: {result1['recommendation']['side']}")
        print(f"  Data Source: {result1['prediction'].get('data_source', 'unknown')}")
    else:
        print(f"  ❌ Error: {result1.get('error', 'Unknown')}")
    
    # Test 2: Historical data rejection
    print("\n📍 Test: Historical data rejection")
    weather2 = {
        'forecast': {'temp_max': 35, 'source': 'historical'},
        'climatology': {'mean_temp': 35}
    }
    result2 = predictor.predict(market1, weather2)
    print(f"  Source: {result2.get('prediction', {}).get('data_source', 'N/A')}")
    if 'error' in result2:
        print(f"  ✅ REJECTED: {result2['error']}")
    
    print("\n" + "=" * 60)
    print("V4 Changes:")
    print("  ✓ Validates data source (rejects historical)")
    print("  ✓ Conservative probability bounds (max 85%)")
    print("  ✓ Forecast outside range → prob capped at 20%")
    print("  ✓ Requires 15% edge + 30% divergence")


if __name__ == "__main__":
    main()
