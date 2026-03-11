#!/usr/bin/env python3
"""
Market Scanner - Finds weather prediction markets on Polymarket
"""
import os
import re
import json
from datetime import datetime, timedelta
from typing import List, Dict, Optional
from dotenv import load_dotenv

load_dotenv()

# Weather-related keywords
WEATHER_KEYWORDS = [
    'temperature', 'temp', 'precipitation', 'rain', 'rainfall', 'snow', 'snowfall',
    'hurricane', 'storm', 'wind', 'heat', 'cold', 'freeze', 'frost',
    'weather', 'fahrenheit', 'celsius', 'degrees', 'high of', 'low of',
    'above', 'below', 'exceed', 'reach'
]

class MarketScanner:
    def __init__(self):
        self.api_key = os.getenv("CLOB_API_KEY")
        self.api_secret = os.getenv("CLOB_SECRET")
        self.api_passphrase = os.getenv("CLOB_PASSPHRASE")
        
    def fetch_markets(self) -> List[Dict]:
        """Fetch all active markets from Polymarket"""
        try:
            from py_clob_client.client import ClobClient
            from py_clob_client.clob_types import ApiCreds
            
            host = "https://clob.polymarket.com"
            chain_id = 137
            
            creds = ApiCreds(api_key=self.api_key, api_secret=self.api_secret, 
                           api_passphrase=self.api_passphrase)
            client = ClobClient(host, key=None, chain_id=chain_id, creds=creds)
            
            print("📡 Fetching markets from Polymarket...")
            response = client.get_markets()
            markets = response.get('data', [])
            print(f"✅ Fetched {len(markets)} total markets")
            return markets
            
        except Exception as e:
            print(f"❌ Error fetching markets: {e}")
            return []
    
    def is_weather_market(self, market: Dict) -> bool:
        """Check if market is weather-related"""
        question = market.get('question', '').lower()
        description = market.get('description', '').lower()
        text = f"{question} {description}"
        
        return any(keyword in text for keyword in WEATHER_KEYWORDS)
    
    def parse_location(self, question: str) -> Optional[Dict]:
        """Extract location from market question"""
        # Common patterns
        patterns = [
            r'(?:in|for|at)\s+([A-Za-z\s]+?)(?:\s+on|\s+by|\s+in\s+\d{4}|\?|$)',
            r'([A-Z][a-z]+(?:\s[A-Z][a-z]+)?)\s+(?:have|reach|hit|exceed)',
            r'(?:will\s+)([A-Z][a-z]+(?:\s[A-Z][a-z]+)?)',
        ]
        
        for pattern in patterns:
            match = re.search(pattern, question)
            if match:
                location_str = match.group(1).strip()
                # Common city mappings
                city_coords = {
                    'new york': {'city': 'New York', 'lat': 40.71, 'lon': -74.01, 'country': 'US'},
                    'nyc': {'city': 'New York', 'lat': 40.71, 'lon': -74.01, 'country': 'US'},
                    'los angeles': {'city': 'Los Angeles', 'lat': 34.05, 'lon': -118.24, 'country': 'US'},
                    'la': {'city': 'Los Angeles', 'lat': 34.05, 'lon': -118.24, 'country': 'US'},
                    'chicago': {'city': 'Chicago', 'lat': 41.88, 'lon': -87.63, 'country': 'US'},
                    'miami': {'city': 'Miami', 'lat': 25.76, 'lon': -80.19, 'country': 'US'},
                    'houston': {'city': 'Houston', 'lat': 29.76, 'lon': -95.37, 'country': 'US'},
                    'boston': {'city': 'Boston', 'lat': 42.36, 'lon': -71.06, 'country': 'US'},
                    'london': {'city': 'London', 'lat': 51.51, 'lon': -0.13, 'country': 'UK'},
                    'paris': {'city': 'Paris', 'lat': 48.86, 'lon': 2.35, 'country': 'FR'},
                    'tokyo': {'city': 'Tokyo', 'lat': 35.68, 'lon': 139.69, 'country': 'JP'},
                }
                
                location_lower = location_str.lower()
                if location_lower in city_coords:
                    return city_coords[location_lower]
                
                # Return generic location
                return {'city': location_str, 'lat': None, 'lon': None, 'country': 'Unknown'}
        
        return None
    
    def parse_threshold(self, question: str) -> Optional[Dict]:
        """Extract threshold from question - handles ranges and different metric types"""
        q_lower = question.lower()
        
        # Determine metric type
        metric_type = 'temperature'
        if any(x in q_lower for x in ['snow', 'snowfall']):
            metric_type = 'snow'
        elif any(x in q_lower for x in ['rain', 'rainfall', 'precipitation']):
            metric_type = 'precipitation'
        
        # Check if it's an "or below" threshold (e.g., "63°F or below", "63 or below")
        below_patterns = [
            r'(\d+(?:\.\d+)?)\s*(?:°|degrees|°f|°c)?\s*or below',
            r'(\d+(?:\.\d+)?)\s*(?:°|degrees|°f|°c)?\s*or lower',
            r'(?:below|under)\s*(\d+(?:\.\d+)?)',
            r'at most\s*(\d+(?:\.\d+)?)',
            r'≤\s*(\d+(?:\.\d+)?)',
            r'<\s*(\d+(?:\.\d+)?)',
        ]
        
        for pattern in below_patterns:
            match = re.search(pattern, q_lower)
            if match:
                value = float(match.group(1))
                unit = 'C' if '°c' in q_lower or 'celsius' in q_lower else 'F'
                return {
                    'value': value,
                    'unit': unit,
                    'direction': 'below',
                    'market_type': metric_type
                }
        
        # Check if it's an "or above" threshold
        above_patterns = [
            r'(\d+(?:\.\d+)?)\s*(?:°|degrees|°f|°c)?\s*or above',
            r'(\d+(?:\.\d+)?)\s*(?:°|degrees|°f|°c)?\s*or higher',
            r'(?:above|over|exceed)\s*(\d+(?:\.\d+)?)',
            r'at least\s*(\d+(?:\.\d+)?)',
            r'≥\s*(\d+(?:\.\d+)?)',
            r'>\s*(\d+(?:\.\d+)?)',
        ]
        
        for pattern in above_patterns:
            match = re.search(pattern, q_lower)
            if match:
                value = float(match.group(1))
                unit = 'C' if '°c' in q_lower or 'celsius' in q_lower else 'F'
                return {
                    'value': value,
                    'unit': unit,
                    'direction': 'above',
                    'market_type': metric_type
                }
        
        # Range patterns (e.g., "30-35 degrees", "8-10 inches", "between 30 and 35")
        range_patterns = [
            (r'between\s+(\d+(?:\.\d+)?)\s+(?:and|to)\s+(\d+(?:\.\d+)?)', 'between'),
            (r'(\d+(?:\.\d+)?)\s*[-–]\s*(\d+(?:\.\d+)?)\s*(?:°|degrees|inches|in)?', 'between'),
        ]
        
        for pattern, direction in range_patterns:
            match = re.search(pattern, q_lower)
            if match:
                low_val = match.group(1)
                high_val = match.group(2)
                unit = 'C' if '°c' in q_lower or 'celsius' in q_lower else 'F'
                if metric_type in ['snow', 'precipitation']:
                    unit = 'inches'
                return {
                    'value': f"{low_val}-{high_val}",
                    'unit': unit,
                    'direction': direction,
                    'market_type': metric_type,
                    'low': float(low_val),
                    'high': float(high_val)
                }
        
        return None
    
    def parse_target_date(self, question: str) -> Optional[str]:
        """Extract target date from question"""
        import re
        from datetime import datetime
        
        # Date patterns
        patterns = [
            r'(January|February|March|April|May|June|July|August|September|October|November|December)\s+(\d{1,2})[,\s]+(\d{4})',
            r'(\d{4})[-/](\d{1,2})[-/](\d{1,2})',
            r'(\d{1,2})[-/](\d{1,2})[-/](\d{4})',
        ]
        
        month_names = {
            'january': 1, 'february': 2, 'march': 3, 'april': 4,
            'may': 5, 'june': 6, 'july': 7, 'august': 8,
            'september': 9, 'october': 10, 'november': 11, 'december': 12
        }
        
        for pattern in patterns:
            match = re.search(pattern, question, re.IGNORECASE)
            if match:
                groups = match.groups()
                try:
                    if groups[0].lower() in month_names:
                        month = month_names[groups[0].lower()]
                        day = int(groups[1])
                        year = int(groups[2])
                    else:
                        year = int(groups[0])
                        month = int(groups[1])
                        day = int(groups[2])
                    
                    return f"{year:04d}-{month:02d}-{day:02d}"
                except:
                    continue
        
        return None
    
    def calculate_score(self, market: Dict) -> float:
        """Calculate opportunity score (0-100)"""
        score = 0.0
        
        # Liquidity score (up to 40 points)
        liquidity = market.get('volume', 0)
        if liquidity >= 500000:
            score += 40
        elif liquidity >= 100000:
            score += 30
        elif liquidity >= 50000:
            score += 20
        elif liquidity >= 10000:
            score += 10
        
        # Uncertainty score - markets priced near 0.5 are more uncertain (up to 30 points)
        try:
            tokens = market.get('tokens', [])
            if len(tokens) >= 2:
                yes_price = float(tokens[0].get('price', 0.5))
                # Distance from 0.5 - lower means more uncertainty
                uncertainty = abs(yes_price - 0.5)
                score += (0.5 - uncertainty) * 60  # Max 30 points
        except:
            pass
        
        # Time urgency (up to 30 points)
        end_date = market.get('end_date_iso', '')
        if end_date:
            try:
                end = datetime.fromisoformat(end_date.replace('Z', '+00:00'))
                days_remaining = (end - datetime.now()).days
                if days_remaining <= 1:
                    score += 30
                elif days_remaining <= 3:
                    score += 20
                elif days_remaining <= 7:
                    score += 10
            except:
                pass
        
        return min(100, max(0, score))
    
    def scan(self, min_score: float = 70.0) -> List[Dict]:
        """Main scan method - find weather markets"""
        all_markets = self.fetch_markets()
        weather_markets = []
        
        print(f"🔍 Filtering {len(all_markets)} markets for weather-related...")
        
        for market in all_markets:
            if not self.is_weather_market(market):
                continue
            
            # Calculate score
            score = self.calculate_score(market)
            
            if score >= min_score:
                # Parse metadata
                question = market.get('question', '')
                location = self.parse_location(question)
                threshold = self.parse_threshold(question)
                target_date = self.parse_target_date(question)
                
                weather_market = {
                    'market_id': market.get('condition_id', market.get('id', 'unknown')),
                    'question': question,
                    'location': location or {'city': 'Unknown', 'lat': None, 'lon': None, 'country': 'Unknown'},
                    'threshold': threshold,
                    'target_date': target_date,
                    'current_price_yes': float(market.get('tokens', [{}])[0].get('price', 0)) if market.get('tokens') else 0,
                    'current_price_no': float(market.get('tokens', [{}])[1].get('price', 0)) if len(market.get('tokens', [])) > 1 else 0,
                    'liquidity_usd': market.get('volume', 0),
                    'volume_24h': market.get('volume_24h', 0),
                    'days_to_resolution': self._days_to_resolution(market.get('end_date_iso', '')),
                    'score': score,
                    'status': 'pending_analysis'
                }
                
                weather_markets.append(weather_market)
        
        # Sort by score
        weather_markets.sort(key=lambda x: x['score'], reverse=True)
        
        print(f"✅ Found {len(weather_markets)} weather markets with score >= {min_score}")
        return weather_markets
    
    def _days_to_resolution(self, end_date_iso: str) -> int:
        """Calculate days to resolution"""
        if not end_date_iso:
            return 999
        try:
            end = datetime.fromisoformat(end_date_iso.replace('Z', '+00:00'))
            days = (end - datetime.now()).days
            return max(0, days)
        except:
            return 999
    
    def save_markets(self, markets: List[Dict], filepath: str = 'data/markets/discovery_queue.jsonl'):
        """Save discovered markets to queue file"""
        os.makedirs(os.path.dirname(filepath), exist_ok=True)
        
        with open(filepath, 'w') as f:
            for market in markets:
                f.write(json.dumps(market) + '\n')
        
        print(f"💾 Saved {len(markets)} markets to {filepath}")


def main():
    scanner = MarketScanner()
    markets = scanner.scan(min_score=50.0)  # Lower threshold for testing
    
    if markets:
        print("\n📊 Top Weather Markets:")
        for i, m in enumerate(markets[:5], 1):
            print(f"\n{i}. {m['question'][:70]}...")
            print(f"   Score: {m['score']:.0f} | Yes: ${m['current_price_yes']:.2f} | Liquidity: ${m['liquidity_usd']:,.0f}")
            if m['location']['city'] != 'Unknown':
                print(f"   Location: {m['location']['city']}")
            if m['threshold']:
                print(f"   Threshold: {m['threshold']['direction']} {m['threshold']['value']}°{m['threshold']['unit']}")
            if m['target_date']:
                print(f"   Target Date: {m['target_date']}")
        
        scanner.save_markets(markets)
    else:
        print("❌ No weather markets found meeting criteria")


if __name__ == "__main__":
    main()