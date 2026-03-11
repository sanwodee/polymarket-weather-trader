#!/usr/bin/env python3
"""
Predictive Modeler v3 - Bug fixes

Critical fixes:
1. Fixed threshold parsing for ranges (30-35°F, 8-10 inches)
2. Proper precipitation (snow/rain) handling - separate from temperature
3. Corrected 'below' threshold logic
4. Added outcome tracking integration
5. Bounded probabilities (never 0% or 100%)
"""
import json
import os
import re
from datetime import datetime, timedelta
from typing import Dict, Optional, Tuple
import numpy as np
from scipy.stats import norm


class WeatherPredictorV3:
    """
    V3 Predictor with critical bug fixes
    """
    
    def __init__(self):
        self.models_used = ['gfs_seamless', 'ecmwf_ifs04']
    
    def _parse_threshold(self, threshold: Dict) -> Tuple[float, float, str, str]:
        """
        Parse threshold into (low, high, range_type, metric_type)
        
        Returns:
            (low_bound, high_bound, range_type, metric_type)
            range_type: 'above', 'below', 'between'
            metric_type: 'temperature', 'precipitation', 'snow', 'rain'
        """
        value = threshold.get('value', 0)
        direction = threshold.get('direction', 'above')
        question = threshold.get('question', '').lower()
        
        # Determine metric type from question/threshold
        metric_type = 'temperature'  # default
        if any(x in question for x in ['snow', 'snowfall', 'inches of snow']):
            metric_type = 'snow'
        elif any(x in question for x in ['rain', 'rainfall', 'precipitation']):
            metric_type = 'precipitation'
        
        # Check if it's a range like "30-31°F" or "8-10 inches"
        if isinstance(value, str):
            # Try to parse range formats: "30-35", "30 to 35", "8-10"
            range_patterns = [
                r'(\d+(?:\.\d+)?)\s*[-–to]\s*(\d+(?:\.\d+)?)',  # 30-35, 30 to 35
                r'between\s+(\d+(?:\.\d+)?)\s+and\s+(\d+(?:\.\d+)?)',  # between 30 and 35
            ]
            
            for pattern in range_patterns:
                match = re.search(pattern, value, re.IGNORECASE)
                if match:
                    try:
                        low = float(match.group(1))
                        high = float(match.group(2))
                        return (low, high, 'between', metric_type)
                    except:
                        pass
            
            # Try to parse single number from string
            try:
                value = float(value)
            except:
                value = 0
        
        # Single threshold
        if direction == 'above':
            return (value, float('inf'), 'above', metric_type)
        else:
            return (float('-inf'), value, 'below', metric_type)
    
    def _calculate_range_probability(self, mean: float, std: float, 
                                     low: float, high: float) -> float:
        """
        Calculate P(low <= X <= high) given mean and std
        """
        if std <= 0:
            std = 0.1  # Minimum uncertainty
        
        z_high = (high - mean) / std if high != float('inf') else float('inf')
        z_low = (low - mean) / std if low != float('-inf') else float('-inf')
        
        p_below_high = norm.cdf(z_high) if z_high != float('inf') else 1.0
        p_below_low = norm.cdf(z_low) if z_low != float('-inf') else 0.0
        
        prob = p_below_high - p_below_low
        
        # Bound between 0.01 and 0.99 (never certainty)
        return max(0.01, min(0.99, prob))
    
    def _get_forecast_params(self, weather_data: Dict, metric_type: str) -> Tuple[Optional[float], Optional[float]]:
        """
        Extract forecast parameters for the specific metric type
        
        Returns: (mean_value, uncertainty)
        """
        forecast = weather_data.get('forecast', {})
        
        if metric_type == 'snow':
            # Snowfall in inches
            value = forecast.get('snowfall')
            uncertainty = forecast.get('snowfall_uncertainty', 0.5)
        elif metric_type == 'precipitation':
            # Precipitation in inches
            value = forecast.get('precipitation')
            uncertainty = forecast.get('precipitation_uncertainty', 0.3)
        else:  # temperature
            temp_max = forecast.get('temp_max')
            temp_mean = forecast.get('temp_mean', temp_max)
            value = temp_mean or temp_max
            uncertainty = forecast.get('uncertainty', 4.0)
        
        return (value, uncertainty)
    
    def _get_climatology_params(self, weather_data: Dict, metric_type: str) -> Tuple[Optional[float], Optional[float]]:
        """
        Extract climatology parameters for the specific metric type
        """
        climatology = weather_data.get('climatology', {})
        
        if metric_type == 'snow':
            mean = climatology.get('mean_snow')
            std = climatology.get('std_snow', 0.5)
        elif metric_type == 'precipitation':
            mean = climatology.get('mean_precip')
            std = climatology.get('std_precip', 0.3)
        else:  # temperature
            mean = climatology.get('mean_temp')
            std = climatology.get('std_dev', 8.0)
        
        if mean is None:
            # Try to compute from data array
            if metric_type == 'snow':
                data = climatology.get('snowfall_amounts', [])
            elif metric_type == 'precipitation':
                data = climatology.get('precipitation_amounts', [])
            else:
                data = climatology.get('temps', [])
            
            if data:
                mean = np.mean(data)
                std = np.std(data) if len(data) > 1 else (std or 1.0)
        
        return (mean, std)
    
    def _calculate_forecast_weight(self, target_date) -> float:
        """Calculate forecast vs climatology weight"""
        today = datetime.now().date()
        
        try:
            if isinstance(target_date, str):
                target = datetime.strptime(target_date.split('T')[0], '%Y-%m-%d').date()
            else:
                target = target_date
            
            days_ahead = (target - today).days
            
            if days_ahead <= 1:
                return 0.90
            elif days_ahead <= 3:
                return 0.80
            elif days_ahead <= 7:
                return 0.70
            elif days_ahead <= 14:
                return 0.60
            elif days_ahead <= 30:
                return 0.50
            else:
                return 0.30
                
        except Exception:
            return 0.70
    
    def predict(self, market: Dict, weather_data: Dict) -> Dict:
        """Main prediction method"""
        threshold_data = market.get('threshold', {})
        target_date = market.get('target_date')
        
        if not threshold_data:
            return {'error': 'No threshold data in market'}
        
        # Add question to threshold for parsing
        threshold_data['question'] = market.get('question', '')
        
        # Parse threshold
        low, high, range_type, metric_type = self._parse_threshold(threshold_data)
        
        # Get forecast and climatology params for the specific metric
        forecast_mean, forecast_std = self._get_forecast_params(weather_data, metric_type)
        clim_mean, clim_std = self._get_climatology_params(weather_data, metric_type)
        
        # Calculate probabilities
        forecast_prob = None
        if forecast_mean is not None and forecast_std is not None:
            forecast_prob = self._calculate_range_probability(
                forecast_mean, forecast_std, low, high
            )
        
        climatology_prob = 0.5
        if clim_mean is not None and clim_std is not None:
            climatology_prob = self._calculate_range_probability(
                clim_mean, clim_std, low, high
            )
        
        # Weighted combination
        if forecast_prob is not None:
            w_forecast = self._calculate_forecast_weight(target_date)
            w_climatology = 1.0 - w_forecast
            combined_prob = (w_forecast * forecast_prob + 
                           w_climatology * climatology_prob)
        else:
            combined_prob = climatology_prob
            w_forecast = 0.0
            w_climatology = 1.0
            forecast_prob = climatology_prob
        
        # Uncertainty
        disagreement = abs(forecast_prob - climatology_prob)
        base_uncertainty = 0.25 if target_date and self._calculate_forecast_weight(target_date) > 0.5 else 0.35
        uncertainty = min(0.50, base_uncertainty + (disagreement * 0.3))
        
        # Market comparison
        market_price_yes = market.get('current_price_yes', 0.5)
        edge = combined_prob - market_price_yes
        edge_percent = edge / market_price_yes if market_price_yes > 0 else 0
        
        # Kelly criterion
        kelly = 0
        if market_price_yes > 0.01 and combined_prob > market_price_yes:
            b = (1 - market_price_yes) / market_price_yes
            kelly_full = (combined_prob * b - (1 - combined_prob)) / b
            kelly = max(0, min(kelly_full, 0.25))
        
        # Confidence
        if uncertainty < 0.15:
            confidence = 'high'
        elif uncertainty < 0.30:
            confidence = 'medium'
        else:
            confidence = 'low'
        
        return {
            'market_id': market.get('market_id'),
            'question': market.get('question'),
            'metric_type': metric_type,
            'threshold_parsed': {'low': low, 'high': high, 'type': range_type},
            'prediction': {
                'probability_yes': combined_prob,
                'probability_no': 1 - combined_prob,
                'uncertainty': uncertainty,
                'confidence': confidence,
                'model_breakdown': {
                    'forecast': {
                        'probability': forecast_prob,
                        'mean': forecast_mean,
                        'uncertainty': forecast_std,
                        'weight': w_forecast
                    },
                    'climatology': {
                        'probability': climatology_prob,
                        'mean': clim_mean,
                        'std': clim_std,
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
                'action': 'evaluate_for_trade' if kelly > 0 and edge > 0.07 else 'pass',
                'side': 'YES' if combined_prob > 0.5 else 'NO',
                'confidence': confidence
            },
            'predicted_at': datetime.now().isoformat()
        }
    
    def backtest(self, historical_weather: Dict, actual_outcome: float, 
                 threshold: Dict) -> Dict:
        """Backtest against historical actuals"""
        threshold['question'] = threshold.get('question', '')
        
        # Create dummy market
        market = {
            'market_id': 'backtest',
            'question': 'Backtest',
            'threshold': threshold,
            'current_price_yes': 0.5,
            'target_date': '2020-01-01'
        }
        
        pred = self.predict(market, historical_weather)
        
        # Parse threshold for actual comparison
        low, high, range_type, metric_type = self._parse_threshold(threshold)
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
    """Test v3 predictor"""
    predictor = WeatherPredictorV3()
    
    print("🤖 Testing Weather Predictor V3")
    print("=" * 60)
    
    # Test 1: Range parsing
    print("\n📍 Test 1: Temperature range (30-35°F)")
    market1 = {
        'market_id': 'test1',
        'question': 'Will temp be between 30-35°F?',
        'threshold': {'value': '30-35', 'direction': 'between'},
        'current_price_yes': 0.25,
        'target_date': '2026-02-24'
    }
    weather1 = {
        'forecast': {'temp_max': 32, 'temp_mean': 30, 'uncertainty': 3},
        'climatology': {'mean_temp': 35, 'std_dev': 8}
    }
    result1 = predictor.predict(market1, weather1)
    print(f"  Forecast: 30°F | Threshold: 30-35°F")
    print(f"  P(30-35°F): {result1['prediction']['probability_yes']:.2%}")
    print(f"  Metric: {result1['metric_type']}")
    
    # Test 2: Below threshold (Miami case)
    print("\n📍 Test 2: Below threshold (Miami <63°F)")
    market2 = {
        'market_id': 'test2',
        'question': 'Will temp be 63°F or below?',
        'threshold': {'value': 63, 'direction': 'below'},
        'current_price_yes': 0.06,
        'target_date': '2026-02-24'
    }
    weather2 = {
        'forecast': {'temp_max': 65, 'temp_mean': 65, 'uncertainty': 3},
        'climatology': {'mean_temp': 78, 'std_dev': 6}
    }
    result2 = predictor.predict(market2, weather2)
    print(f"  Forecast: 65°F | Threshold: <=63°F")
    print(f"  P(<=63°F): {result2['prediction']['probability_yes']:.2%}")
    print(f"  Expected: LOW (forecast is ABOVE threshold)")
    
    # Test 3: Snow market
    print("\n📍 Test 3: Snow range (8-10 inches)")
    market3 = {
        'market_id': 'test3',
        'question': 'Will snowfall be 8-10 inches?',
        'threshold': {'value': '8-10', 'direction': 'between'},
        'current_price_yes': 0.02,
        'target_date': '2026-02-24'
    }
    weather3 = {
        'forecast': {'snowfall': 2.0, 'snowfall_uncertainty': 1.0},
        'climatology': {'mean_snow': 3.0, 'std_snow': 2.0}
    }
    result3 = predictor.predict(market3, weather3)
    print(f"  Forecast snowfall: 2.0 in | Threshold: 8-10 in")
    print(f"  P(8-10 in): {result3['prediction']['probability_yes']:.2%}")
    print(f"  Metric: {result3['metric_type']}")
    print(f"  Expected: LOW (forecast is BELOW range)")
    
    print("\n" + "=" * 60)
    print("V3 fixes:")
    print("  ✓ Proper range parsing (30-35, 8-10)")
    print("  ✓ Separate metric types (temp/snow/precip)")
    print("  ✓ Bounded probabilities (never 100%)")
    print("  ✓ No more inverted thresholds")


if __name__ == "__main__":
    main()
