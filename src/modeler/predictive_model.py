#!/usr/bin/env python3
"""
Predictive Modeler - Combines climatology + ensemble forecasts
Phase 1: Simple weighted model (no ML)
"""
import json
import os
from datetime import datetime
from typing import Dict, Optional
import numpy as np

class WeatherPredictor:
    """
    Phase 1 Predictor: Weighted ensemble of climatology + forecast
    
    Weights:
    - Climatology (historical base rate): 40%
    - Ensemble forecast: 60%
    """
    
    def __init__(self, weights=None):
        # Phase 1 weights (Phase 6 can tune these)
        self.weights = weights or {
            'climatology': 0.40,
            'forecast': 0.60
        }
        
    def calculate_ensemble_probability(self, forecast: Dict, threshold: Dict) -> Dict:
        """
        Calculate probability from ensemble forecast
        
        Args:
            forecast: Dict with temp_max, temp_mean, etc.
            threshold: Dict with value, direction
        
        Returns:
            Probability and confidence interval
        """
        temp_max = forecast.get('temp_max')
        
        if temp_max is None:
            return {
                'probability': None,
                'confidence_interval': (None, None),
                'uncertainty': 1.0
            }
        
        threshold_value = threshold.get('value', 0)
        direction = threshold.get('direction', 'above')
        
        # For Phase 1, use a simple approach:
        # If forecast temp is above threshold, high probability
        # If below, low probability
        # Use distance from threshold as confidence measure
        
        # Assume forecast uncertainty of ±3°F (based on ensemble spread typical)
        uncertainty = 3.0  # degrees
        
        if direction == 'above':
            # P(temp >= threshold)
            # Use normal distribution assumption
            z_score = (temp_max - threshold_value) / uncertainty
            from scipy.stats import norm
            prob = 1 - norm.cdf(-z_score)  # P(Z > -z) = 1 - P(Z < -z)
        else:
            # P(temp <= threshold)  
            z_score = (threshold_value - temp_max) / uncertainty
            from scipy.stats import norm
            prob = norm.cdf(z_score)
        
        # Confidence interval based on uncertainty
        if direction == 'above':
            ci_low = max(0, prob - 0.15)
            ci_high = min(1, prob + 0.15)
        else:
            ci_low = max(0, prob - 0.15)
            ci_high = min(1, prob + 0.15)
        
        return {
            'probability': prob,
            'confidence_interval': (ci_low, ci_high),
            'uncertainty': uncertainty / (threshold_value + 1),  # Relative uncertainty
            'forecast_temp': temp_max,
            'threshold': threshold_value
        }
    
    def combine_predictions(self, climatology_prob: float, forecast_prob: float) -> Dict:
        """
        Combine climatology and forecast using weighted average
        
        Args:
            climatology_prob: Historical base rate (0-1)
            forecast_prob: Ensemble forecast probability (0-1)
        
        Returns:
            Combined prediction with uncertainty
        """
        if climatology_prob is None or forecast_prob is None:
            return {
                'probability': None,
                'uncertainty': 1.0,
                'confidence_interval': (None, None),
                'components': {}
            }
        
        # Weighted average
        w_climo = self.weights['climatology']
        w_forecast = self.weights['forecast']
        
        combined_prob = (w_climo * climatology_prob + 
                        w_forecast * forecast_prob)
        
        # Uncertainty is higher when predictions disagree
        disagreement = abs(climatology_prob - forecast_prob)
        base_uncertainty = 0.15  # Base uncertainty
        disagreement_bonus = disagreement * 0.5  # More disagreement = more uncertainty
        uncertainty = base_uncertainty + disagreement_bonus
        
        # Confidence interval
        ci_low = max(0, combined_prob - 1.96 * uncertainty)
        ci_high = min(1, combined_prob + 1.96 * uncertainty)
        
        return {
            'probability': combined_prob,
            'uncertainty': uncertainty,
            'confidence_interval': (ci_low, ci_high),
            'components': {
                'climatology': {
                    'probability': climatology_prob,
                    'weight': w_climo
                },
                'forecast': {
                    'probability': forecast_prob,
                    'weight': w_forecast
                }
            },
            'disagreement': disagreement
        }
    
    def predict(self, market: Dict, weather_data: Dict) -> Dict:
        """
        Main prediction method
        
        Args:
            market: Market dict with threshold, target_date, location
            weather_data: Dict with climatology and forecast
        
        Returns:
            Prediction result
        """
        threshold = market.get('threshold', {})
        location = market.get('location', {})
        
        if not threshold:
            return {'error': 'No threshold data in market'}
        
        # Get climatology probability
        climatology = weather_data.get('climatology', {})
        climatology_prob = climatology.get('baseline_probability_combined', 
                                          climatology.get('baseline_probability_empirical', 0.5))
        
        if climatology_prob is None:
            climatology_prob = 0.5  # Default if no data
        
        # Get forecast probability
        forecast = weather_data.get('forecast', {})
        forecast_result = self.calculate_ensemble_probability(forecast, threshold)
        forecast_prob = forecast_result.get('probability', 0.5)
        
        if forecast_prob is None:
            # Fall back to climatology only
            forecast_prob = climatology_prob
        
        # Combine
        prediction = self.combine_predictions(climatology_prob, forecast_prob)
        
        # Compare to market
        market_price_yes = market.get('current_price_yes', 0.5)
        model_prob = prediction['probability']
        
        if model_prob is None:
            return {
                'error': 'Could not calculate probability',
                'market_id': market.get('market_id'),
                'status': 'failed'
            }
        
        # Calculate edge
        edge = model_prob - market_price_yes
        edge_percent = edge / market_price_yes if market_price_yes > 0 else 0
        
        # Calculate Kelly fraction
        if market_price_yes > 0 and model_prob > market_price_yes:
            # b = odds = (1 - price) / price
            b = (1 - market_price_yes) / market_price_yes
            kelly = (model_prob * b - (1 - model_prob)) / b
            kelly = max(0, kelly)  # Don't bet if negative
        else:
            kelly = 0
        
        return {
            'market_id': market.get('market_id'),
            'question': market.get('question'),
            'prediction': {
                'probability_yes': model_prob,
                'probability_no': 1 - model_prob,
                'confidence_interval': prediction['confidence_interval'],
                'uncertainty': prediction['uncertainty'],
                'model_breakdown': prediction['components']
            },
            'market_comparison': {
                'market_price_yes': market_price_yes,
                'model_price_yes': model_prob,
                'divergence': edge,
                'edge_percent': edge_percent,
                'kelly_fraction': kelly
            },
            'recommendation': {
                'action': 'evaluate_for_trade' if kelly > 0 and edge > 0.07 else 'pass',
                'side': 'YES' if model_prob > 0.5 else 'NO',
                'confidence': 'high' if prediction['uncertainty'] < 0.15 else 'medium' if prediction['uncertainty'] < 0.25 else 'low'
            },
            'predicted_at': datetime.now().isoformat()
        }
    
    def save_prediction(self, prediction: Dict, filepath: str = 'data/predictions'):
        """Save prediction to file"""
        import os
        os.makedirs(filepath, exist_ok=True)
        
        market_id = prediction.get('market_id', 'unknown')
        output_file = os.path.join(filepath, f"{market_id}_pred.json")
        
        with open(output_file, 'w') as f:
            json.dump(prediction, f, indent=2)
        
        return output_file


def main():
    """Test the predictor"""
    predictor = WeatherPredictor()
    
    # Test scenario
    market = {
        'market_id': 'test_market',
        'question': 'Will NYC have above 90°F on July 4, 2025?',
        'threshold': {'value': 90, 'unit': 'F', 'direction': 'above'},
        'current_price_yes': 0.34,
        'location': {'city': 'New York', 'lat': 40.71, 'lon': -74.01}
    }
    
    weather_data = {
        'climatology': {
            'baseline_probability_combined': 0.28,
            'mean_temp': 84.3,
            'std_dev': 6.2
        },
        'forecast': {
            'temp_max': 92,
            'temp_mean': 88
        }
    }
    
    print("🤖 Testing Weather Predictor (Phase 1)")
    print(f"Market: {market['question']}")
    print(f"Market Price (Yes): {market['current_price_yes']}")
    print()
    
    result = predictor.predict(market, weather_data)
    
    print(f"Model P(Yes): {result['prediction']['probability_yes']:.2%}")
    print(f"Edge: {result['market_comparison']['edge_percent']:.1%}")
    print(f"Kelly Fraction: {result['market_comparison']['kelly_fraction']:.2%}")
    print(f"Recommendation: {result['recommendation']['action']}")


if __name__ == "__main__":
    main()