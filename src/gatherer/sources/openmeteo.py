#!/usr/bin/env python3
"""
Open-Meteo Data Gatherer - FREE weather data (no API key required)
https://open-meteo.com/
"""
import requests
import json
import os
from datetime import datetime, timedelta
from typing import Dict, Optional, List
import time

class OpenMeteoGatherer:
    """Gather weather data from Open-Meteo (free, no API key)"""
    
    BASE_URL = "https://api.open-meteo.com/v1"
    
    def __init__(self, cache_dir: str = 'data/weather'):
        self.cache_dir = cache_dir
        os.makedirs(cache_dir, exist_ok=True)
        self.session = requests.Session()
        
    def _cache_path(self, lat: float, lon: float, date: str) -> str:
        """Generate cache file path"""
        cache_key = f"{lat:.4f}_{lon:.4f}_{date}"
        return os.path.join(self.cache_dir, f"{cache_key}.json")
    
    def _check_cache(self, lat: float, lon: float, date: str) -> Optional[Dict]:
        """Check if data is cached and fresh (1 hour TTL)"""
        cache_path = self._cache_path(lat, lon, date)
        
        if not os.path.exists(cache_path):
            return None
        
        # Check if cache is fresh (1 hour)
        mtime = os.path.getmtime(cache_path)
        if time.time() - mtime > 3600:  # 1 hour
            return None
        
        try:
            with open(cache_path, 'r') as f:
                return json.load(f)
        except:
            return None
    
    def _save_cache(self, lat: float, lon: float, date: str, data: Dict):
        """Save data to cache"""
        cache_path = self._cache_path(lat, lon, date)
        with open(cache_path, 'w') as f:
            json.dump(data, f)
    
    def get_historical(self, lat: float, lon: float, start_date: str, end_date: str) -> Dict:
        """
        Get historical weather data
        
        Args:
            lat: Latitude
            lon: Longitude
            start_date: Start date (YYYY-MM-DD)
            end_date: End date (YYYY-MM-DD)
        
        Returns:
            Dict with historical temperature data
        """
        cache_key = f"{lat:.4f}_{lon:.4f}_{start_date}_{end_date}"
        cache_path = os.path.join(self.cache_dir, f"hist_{cache_key}.json")
        
        # Check cache (30 days TTL for historical)
        if os.path.exists(cache_path):
            mtime = os.path.getmtime(cache_path)
            if time.time() - mtime < 30 * 24 * 3600:  # 30 days
                try:
                    with open(cache_path, 'r') as f:
                        return json.load(f)
                except:
                    pass
        
        url = "https://archive-api.open-meteo.com/v1/archive"
        params = {
            'latitude': lat,
            'longitude': lon,
            'start_date': start_date,
            'end_date': end_date,
            'daily': 'temperature_2m_max,temperature_2m_min,temperature_2m_mean',
            'timezone': 'auto',
            'temperature_unit': 'fahrenheit'
        }
        
        try:
            response = self.session.get(url, params=params, timeout=30)
            response.raise_for_status()
            data = response.json()
            
            # Save to cache
            with open(cache_path, 'w') as f:
                json.dump(data, f)
            
            return data
            
        except Exception as e:
            print(f"❌ Error fetching historical data: {e}")
            return {}
    
    def get_forecast(self, lat: float, lon: float, target_date: str) -> Dict:
        """
        Get forecast for target date with ensemble data
        
        Prioritizes live forecast API over historical data
        
        Args:
            lat: Latitude
            lon: Longitude
            target_date: Target date (YYYY-MM-DD)
        
        Returns:
            Dict with forecast data including ensemble spread
        """
        # Check cache first
        cached = self._check_cache(lat, lon, target_date)
        if cached:
            return cached
        
        # Calculate forecast days needed (compare dates only, not times)
        target = datetime.strptime(target_date, '%Y-%m-%d').date()
        today = datetime.now().date()
        days_ahead = (target - today).days
        
        # For today or future dates, ALWAYS try forecast API first
        if days_ahead >= 0:
            url = f"{self.BASE_URL}/forecast"
            params = {
                'latitude': lat,
                'longitude': lon,
                'daily': 'temperature_2m_max,temperature_2m_min,temperature_2m_mean',
                'forecast_days': min(days_ahead + 1, 16),
                'models': 'gfs_seamless,ecmwf_ifs04',
                'timezone': 'auto',
                'temperature_unit': 'fahrenheit'
            }
            
            try:
                response = self.session.get(url, params=params, timeout=30)
                response.raise_for_status()
                data = response.json()
                
                # Extract forecast for target date
                daily = data.get('daily', {})
                dates = daily.get('time', [])
                
                if target_date in dates:
                    idx = dates.index(target_date)
                    
                    # Handle model-specific keys (model name appended) vs generic keys
                    # e.g., temperature_2m_max_gfs_seamless vs temperature_2m_max
                    def get_temp(key):
                        if key in daily and len(daily[key]) > idx:
                            return daily[key][idx]
                        # Try model-specific keys
                        for model in ['gfs_seamless', 'ecmwf_ifs04']:
                            model_key = f"{key}_{model}"
                            if model_key in daily and len(daily[model_key]) > idx:
                                return daily[model_key][idx]
                        return None
                    
                    temp_max = get_temp('temperature_2m_max')
                    temp_min = get_temp('temperature_2m_min')
                    temp_mean = get_temp('temperature_2m_mean')
                    
                    if temp_max is None:
                        raise ValueError("No temperature data found")
                    
                    forecast = {
                        'date': target_date,
                        'temp_max': temp_max,
                        'temp_min': temp_min,
                        'temp_mean': temp_mean,
                        'latitude': lat,
                        'longitude': lon,
                        'source': 'forecast',
                        'models_used': ['gfs_seamless', 'ecmwf_ifs04'],
                        'generated_at': datetime.now().isoformat()
                    }
                    
                    # Cache the result
                    self._save_cache(lat, lon, target_date, forecast)
                    return forecast
                
            except Exception as e:
                print(f"⚠️ Forecast API failed, falling back to historical: {e}")
        
        # Fallback to historical data (only for past dates or if forecast fails)
        return self.get_historical_day(lat, lon, target_date)
    
    def get_historical_day(self, lat: float, lon: float, target_date: str) -> Dict:
        """Get historical data for a single day"""
        data = self.get_historical(lat, lon, target_date, target_date)
        
        daily = data.get('daily', {})
        dates = daily.get('time', [])
        
        if target_date in dates:
            idx = dates.index(target_date)
            return {
                'date': target_date,
                'temp_max': daily.get('temperature_2m_max', [])[idx],
                'temp_min': daily.get('temperature_2m_min', [])[idx],
                'temp_mean': daily.get('temperature_2m_mean', [])[idx],
                'latitude': lat,
                'longitude': lon,
                'source': 'historical',
                'generated_at': datetime.now().isoformat()
            }
        
        return {'error': f'No historical data for {target_date}'}
    
    def get_historical_for_date(self, lat: float, lon: float, month: int, day: int, 
                                 years: int = 30) -> Dict:
        """
        Get historical temperatures for same date across years (climatology)
        
        Args:
            lat: Latitude
            lon: Longitude
            month: Month (1-12)
            day: Day (1-31)
            years: Number of years to fetch (default 30)
        
        Returns:
            Dict with statistical summary
        """
        current_year = datetime.now().year
        temps = []
        years_fetched = []
        
        # Calculate date range
        end_year = current_year - 1
        start_year = end_year - years + 1
        
        # Build date list
        dates = []
        for year in range(start_year, end_year + 1):
            try:
                date_str = f"{year}-{month:02d}-{day:02d}"
                datetime.strptime(date_str, '%Y-%m-%d')  # Validate
                dates.append(date_str)
            except ValueError:
                # Feb 29 on non-leap years, etc.
                continue
        
        # Fetch in batches (Open-Meteo allows up to 1 year per request? No, check)
        # Actually Open-Meteo archive supports multi-year
        if len(dates) > 0:
            data = self.get_historical(lat, lon, dates[0], dates[-1])
            
            daily = data.get('daily', {})
            all_dates = daily.get('time', [])
            max_temps = daily.get('temperature_2m_max', [])
            
            for i, date in enumerate(all_dates):
                if date in dates and i < len(max_temps):
                    temp = max_temps[i]
                    if temp is not None:
                        temps.append(temp)
                        year = int(date.split('-')[0])
                        years_fetched.append(year)
        
        if len(temps) == 0:
            return {
                'error': 'No historical data available',
                'years_available': 0,
                'threshold_hits': 0,
                'threshold_misses': 0,
                'baseline_probability': None,
                'mean_temp': None,
                'std_dev': None
            }
        
        import numpy as np
        
        mean_temp = np.mean(temps)
        std_dev = np.std(temps)
        
        return {
            'years_available': len(temps),
            'years_fetched': sorted(years_fetched),
            'temps': temps,
            'mean_temp': mean_temp,
            'std_dev': std_dev,
            'min_temp': np.min(temps),
            'max_temp': np.max(temps),
            'percentile_25': np.percentile(temps, 25),
            'percentile_50': np.percentile(temps, 50),
            'percentile_75': np.percentile(temps, 75),
            'percentile_90': np.percentile(temps, 90),
            'percentile_95': np.percentile(temps, 95),
            'source': 'open-meteo',
            'generated_at': datetime.now().isoformat()
        }
    
    def calculate_threshold_probability(self, climatology: Dict, threshold_value: float, 
                                       direction: str = 'above') -> Dict:
        """
        Calculate probability of exceeding/falling below threshold
        
        Args:
            climatology: Historical data from get_historical_for_date
            threshold_value: Temperature threshold
            direction: 'above' or 'below'
        
        Returns:
            Dict with probability calculations
        """
        import numpy as np
        
        temps = climatology.get('temps', [])
        
        if len(temps) == 0:
            return {
                'baseline_probability': None,
                'threshold_hits': 0,
                'threshold_misses': 0
            }
        
        if direction == 'above':
            hits = sum(1 for t in temps if t >= threshold_value)
        else:
            hits = sum(1 for t in temps if t <= threshold_value)
        
        total = len(temps)
        probability = hits / total if total > 0 else 0
        
        # Calculate using normal distribution too
        mean = climatology.get('mean_temp', np.mean(temps))
        std = climatology.get('std_dev', np.std(temps))
        
        from scipy import stats
        if direction == 'above':
            normal_prob = 1 - stats.norm.cdf(threshold_value, mean, std)
        else:
            normal_prob = stats.norm.cdf(threshold_value, mean, std)
        
        return {
            'baseline_probability_empirical': probability,
            'baseline_probability_normal': normal_prob,
            'baseline_probability_combined': (probability + normal_prob) / 2,
            'threshold_hits': hits,
            'threshold_misses': total - hits,
            'years_analyzed': total
        }


def main():
    """Test the gatherer"""
    gatherer = OpenMeteoGatherer()
    
    # Test with NYC coordinates
    lat, lon = 40.71, -74.01
    target_date = "2025-07-04"
    
    print("🌤️ Testing Open-Meteo Gatherer (FREE - no API key)")
    print(f"Location: NYC ({lat}, {lon})")
    print(f"Target Date: {target_date}\n")
    
    # Get forecast
    print("📡 Fetching forecast...")
    forecast = gatherer.get_forecast(lat, lon, target_date)
    print(f"Forecast: {json.dumps(forecast, indent=2)}\n")
    
    # Get climatology (July 4th across 30 years)
    print("📊 Fetching historical climatology (July 4th, 30 years)...")
    climatology = gatherer.get_historical_for_date(lat, lon, 7, 4, years=30)
    print(f"Mean Temp: {climatology.get('mean_temp', 'N/A'):.1f}°F")
    print(f"Std Dev: {climatology.get('std_dev', 'N/A'):.1f}°F")
    print(f"Years Available: {climatology.get('years_available', 0)}\n")
    
    # Calculate threshold probability (e.g., 90°F)
    if climatology.get('temps'):
        prob = gatherer.calculate_threshold_probability(climatology, 90, 'above')
        print(f"🎯 Probability of ≥90°F on July 4th:")
        print(f"   Empirical: {prob['baseline_probability_empirical']:.1%}")
        print(f"   Normal: {prob['baseline_probability_normal']:.1%}")
        print(f"   Combined: {prob['baseline_probability_combined']:.1%}")


if __name__ == "__main__":
    # Try with scipy, but it's optional
    try:
        from scipy import stats
    except ImportError:
        print("⚠️ scipy not installed. Install with: pip install scipy")
        print("Continuing without normal distribution calculations...")
    
    main()