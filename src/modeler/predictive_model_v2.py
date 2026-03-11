#!/usr/bin/env python3
"""
Predictive Modeler v2 - Fixed accuracy issues
Key fixes:
1. Proper forecast weighting (80% for short-term, 20% climatology)
2. Handle temperature ranges (30-31°F) not just thresholds
3. Use actual forecast data with ensemble spread
4. Bounded probabilities (never 0% or 100%)
5. Uncertainty based on forecast horizon
"""
import json
import os
from datetime import datetime, timedelta
from typing import Dict, Optional, Tuple
import numpy as np
from scipy.stats import norm


class WeatherPredictorV2:
    """
    V2 Predictor with improved accuracy
    
    Key insight: Short-term weather is forecast-driven, not climatology-driven
    """
    
    def __init__(self):
        self.models_used = ['gfs_seamless', 'ecmwf_ifs04']
    
    def _parse_threshold_or_range(self, threshold: Dict) -> Tuple[float, float, str]:
        """
        Parse threshold into (low, high, type)
        
        Returns:
            (low_bound, high_bound, range_type)
            range_type: 'above', 'below', 'between'
        """
        value = threshold.get('value', 0)
        direction = threshold.get('direction', 'above')
        
        # Check if it's a range like "30-31°F"
        if isinstance(value, str) and '-' in value:
            try:
                parts = value.split('-')
                low = float(parts[0])
                high = float(parts[1])
                return (low, high, 'between')
            except:
                pass
        
        # Single threshold
        if direction == 'above':
            return (value, float('inf'), 'above')
        else:
            return (float('-inf'), value, 'below')
    
    def _calculate_range_probability(self, mean: float, std: float, 
                                     low: float, high: float) -> float:
        """
        Calculate P(low <= X <= high) given mean and std
        Uses normal distribution assumption
        """
        # Probability of being below high
        p_below_high = norm.cdf((high - mean) / std) if high != float('inf') else 1.0
        # Probability of being below low
        p_below_low = norm.cdf((low - mean) / std) if low != float('-inf') else 0.0
        
        # Probability between low and high
        prob = p_below_high - p_below_low
        
        # Bound between 0.01 and 0.99 (never certainty)
        return max(0.01, min(0.99, prob))
    
    def _get_forecast_params(self, forecast: Dict) -> Tuple[float, float]:
        """
        Extract mean temperature and uncertainty from forecast
        
        Returns: (mean_temp, uncertainty)
        """
        temp_max = forecast.get('temp_max')
        temp_mean = forecast.get('temp_mean', temp_max)
        
        if temp_max is None:
            return (None, None)
        
        # Use ensemble spread if available, otherwise assume ±4°F for 1-day, ±6°F for 3-day, etc.
        uncertainty = forecast.get('uncertainty', 4.0)
        
        return (temp_mean or temp_max, uncertainty)
    
    def _get_climatology_params(self, climatology: Dict) -> Tuple[float, float]:
        """
        Extract mean and std from climatology
        """
        mean = climatology.get('mean_temp')
        std = climatology.get('std_dev', 8.0)  # Default 8°F std dev
        
        if mean is None:
            # Try to compute from temps array
            temps = climatology.get('temps', [])
            if temps:
                mean = np.mean(temps)
                std = np.std(temps)
        
        return (mean, std)
    
    def _calculate_forecast_weight(self, target_date: str) -> float:
        """
        Calculate how much to weight forecast vs climatology
        
        Tomorrow: 90% forecast, 10% climatology
        1 week: 70% forecast, 30% climatology
        1 month: 50% forecast, 50% climatology
        3+ months: 30% forecast, 70% climatology
        """
        today = datetime.now().date()
        
        try:
            if isinstance(target_date, str):
                target = datetime.strptime(target_date.split('T')[0], '%Y-%m-%d').date()
            else:
                target = target_date
            
            days_ahead = (target - today).days
            
            # Weight decreases as we go further out
            if days_ahead <= 1:
                return 0.90  # Tomorrow: 90% forecast
            elif days_ahead <= 3:
                return 0.80  # 2-3 days: 80% forecast
            elif days_ahead <= 7:
                return 0.70  # 4-7 days: 70% forecast
            elif days_ahead <= 14:
                return 0.60  # 2 weeks: 60% forecast
            elif days_ahead <= 30:
                return 0.50  # 1 month: 50% forecast
            else:
                return 0.30  # 3+ months: 30% forecast
                
        except Exception as e:
            # Default to 70% forecast weight
            return 0.70
    
    def predict(self, market: Dict, weather_data: Dict) -> Dict:
        """
        Main prediction method with fixed accuracy
        """
        threshold = market.get('threshold', {})
        target_date = market.get('target_date')
        
        if not threshold:
            return {'error': 'No threshold data in market'}
        
        # Parse the range/threshold
        low, high, range_type = self._parse_threshold_or_range(threshold)
        
        # Get forecast parameters
        forecast = weather_data.get('forecast', {})
        forecast_mean, forecast_std = self._get_forecast_params(forecast)
        
        # Get climatology parameters
        climatology = weather_data.get('climatology', {})
        clim_mean, clim_std = self._get_climatology_params(climatology)
        
        # Calculate forecast probability if we have forecast data
        if forecast_mean is not None and forecast_std is not None:
            forecast_prob = self._calculate_range_probability(
                forecast_mean, forecast_std, low, high
            )
        else:
            # If no forecast, fall back to climatology only
            forecast_prob = None
        
        # Calculate climatology probability if we have data
        if clim_mean is not None and clim_std is not None:
            climatology_prob = self._calculate_range_probability(
                clim_mean, clim_std, low, high
            )
        else:
            climatology_prob = 0.5  # Default to coin flip
        
        # Determine weights based on forecast horizon
        if forecast_prob is not None:
            w_forecast = self._calculate_forecast_weight(target_date)
            w_climatology = 1.0 - w_forecast
            
            # Weighted combination
            combined_prob = (w_forecast * forecast_prob + 
                           w_climatology * climatology_prob)
        else:
            # No forecast, use climatology only
            combined_prob = climatology_prob
            w_forecast = 0.0
            w_climatology = 1.0
            forecast_prob = climatology_prob
        
        # Uncertainty calculation
        # Higher uncertainty when forecast and climatology disagree
        disagreement = abs(forecast_prob - climatology_prob)
        # Base uncertainty depends on days ahead
        base_uncertainty = 0.20 if target_date and self._calculate_forecast_weight(target_date) > 0.5 else 0.30
        uncertainty = base_uncertainty + (disagreement * 0.3)
        uncertainty = min(0.50, uncertainty)  # Cap at 50%
        
        # Market comparison
        market_price_yes = market.get('current_price_yes', 0.5)
        edge = combined_prob - market_price_yes
        edge_percent = edge / market_price_yes if market_price_yes > 0 else 0
        
        # Kelly fraction with max 25% position
        if market_price_yes > 0.01 and combined_prob > market_price_yes:
            b = (1 - market_price_yes) / market_price_yes
            kelly_full = (combined_prob * b - (1 - combined_prob)) / b
            kelly = max(0, min(kelly_full, 0.25))  # Cap at 25%
        else:
            kelly = 0
        
        # Confidence based on uncertainty
        if uncertainty < 0.15:
            confidence = 'high'
        elif uncertainty < 0.30:
            confidence = 'medium'
        else:
            confidence = 'low'
        
        # Recommendation logic
        # Only trade if:
        # 1. Edge > 7%
        # 2. Kelly > 0 (positive EV)
        # 3. Confidence not 'low'
        action = 'evaluate_for_trade' if kelly > 0 and edge > 0.07 and confidence != 'low' else 'pass'
        
        return {
            'market_id': market.get('market_id'),
            'question': market.get('question'),
            'prediction': {
                'probability_yes': combined_prob,
                'probability_no': 1 - combined_prob,
                'uncertainty': uncertainty,
                'confidence': confidence,
                'model_breakdown': {
                    'forecast': {
                        'probability': forecast_prob,
                        'mean_temp': forecast_mean,
                        'uncertainty': forecast_std,
                        'weight': w_forecast
                    },
                    'climatology': {
                        'probability': climatology_prob,
                        'mean_temp': clim_mean,
                        'std_dev': clim_std,
                        'weight': w_climatology
                    }
                }
            },
            'market_comparison': {
                'market_price_yes': market_price_yes,
                'model_price_yes': combined_prob,
                'divergence': edge,
                'edge_percent': edge_percent,
                'kelly_fraction': kelly
            },
            'recommendation': {
                'action': action,
                'side': 'YES' if combined_prob > 0.5 else 'NO',
                'confidence': confidence,
                'reason': f'Forecast weight: {w_forecast:.0%}, Climatology weight: {w_climatology:.0%}'
            },
            'predicted_at': datetime.now().isoformat()
        }
    
    def backtest(self, historical_weather: Dict, actual_outcome: float, 
                 threshold: Dict) -> Dict:
        """
        Backtest the model against historical actuals
        
        Args:
            historical_weather: Weather data as of prediction date
            actual_outcome: Actual temperature that occurred
            threshold: Market threshold definition
        
        Returns:
            Backtest result with accuracy metrics
        """
        # Create dummy market for prediction
        market = {
            'market_id': 'backtest',
            'question': 'Backtest',
            'threshold': threshold,
            'current_price_yes': 0.5,  # Assume fair market
            'target_date': '2020-01-01'
        }
        
        # Get prediction
        pred = self.predict(market, historical_weather)
        
        # Determine if prediction was correct
        low, high, range_type = self._parse_threshold_or_range(threshold)
        actual_in_range = low <= actual_outcome <= high
        
        predicted_yes = pred['prediction']['probability_yes'] > 0.5
        
        correct = (predicted_yes and actual_in_range) or (not predicted_yes and not actual_in_range)
        
        brier_score = (pred['prediction']['probability_yes'] - (1 if actual_in_range else 0)) ** 2
        
        return {
            'prediction': pred['prediction']['probability_yes'],
            'actual_outcome': actual_outcome,
            'actual_in_range': actual_in_range,
            'predicted_yes': predicted_yes,
            'correct': correct,
            'brier_score': brier_score,
            'calibration_error': abs(pred['prediction']['probability_yes'] - (1 if actual_in_range else 0))
        }


def main():
    """Test the improved predictor"""
    predictor = WeatherPredictorV2()
    
    print("🤖 Testing Weather Predictor V2")
    print("=" * 60)
    
    # Test 1: Chicago Feb 23, 2026 scenario (what actually happened)
    print("\n📍 Test 1: Chicago Feb 23 (Actual: 27.5°F)")
    market1 = {
        'market_id': 'test1',
        'question': '30-31°F ?',
        'threshold': {'value': '30-31', 'direction': 'between'},
        'current_price_yes': 0.14,
        'target_date': '2026-02-23'
    }
    weather1 = {
        'forecast': {'temp_max': 28, 'temp_mean': 25, 'uncertainty': 4},
        'climatology': {'mean_temp': 35, 'std_dev': 8}
    }
    result1 = predictor.predict(market1, weather1)
    print(f"  Forecast: 28°F | Climatology: 35°F | Actual: 27.5°F")
    print(f"  P(30-31°F): {result1['prediction']['probability_yes']:.2%}")
    print(f"  Recommendation: {result1['recommendation']['side']}")
    
    # Test 2: Miami Feb 24 scenario
    print("\n📍 Test 2: Miami Feb 24 (Actual: 65.4°F)")
    market2 = {
        'market_id': 'test2',
        'question': '<=63°F ?',
        'threshold': {'value': 63, 'direction': 'below'},
        'current_price_yes': 0.02,
        'target_date': '2026-02-24'
    }
    weather2 = {
        'forecast': {'temp_max': 65, 'temp_mean': 62, 'uncertainty': 3},
        'climatology': {'mean_temp': 78, 'std_dev': 6}
    }
    result2 = predictor.predict(market2, weather2)
    print(f"  Forecast: 65°F | Climatology: 78°F")
    print(f"  P(<=63°F): {result2['prediction']['probability_yes']:.2%}")
    print(f"  Recommendation: {result2['recommendation']['side']}")
    
    print("\n" + "=" * 60)
    print("Key improvements:")
    print("  ✓ Bounded probabilities (never 100%)")
    print("  ✓ Forecast weight based on horizon")
    print("  ✓ Proper range probability calculation")
    print("  ✓ Uncertainty based on forecast spread")


if __name__ == "__main__":
    main()
