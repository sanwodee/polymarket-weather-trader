#!/usr/bin/env python3
"""
Weather Market Scraper - Gets full market data from polymarket.com/predictions/weather
"""
import requests
from bs4 import BeautifulSoup
import json
import re
from typing import List, Dict, Optional
import sys
import os
from datetime import datetime

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
from py_clob_client.client import ClobClient
from py_clob_client.clob_types import ApiCreds

class WeatherMarketScraper:
    """Scraper for Polymarket weather markets with full CLOB data"""
    
    URL = 'https://polymarket.com/predictions/weather'
    
    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
        })
        
        # Init CLOB client
        api_key = os.getenv('CLOB_API_KEY')
        api_secret = os.getenv('CLOB_SECRET')
        api_pass = os.getenv('CLOB_PASSPHRASE')
        
        if api_key and api_secret:
            creds = ApiCreds(api_key=api_key, api_secret=api_secret, api_passphrase=api_pass)
            self.client = ClobClient('https://clob.polymarket.com', key=None, chain_id=137, creds=creds)
        else:
            self.client = None
    
    def scrape_events(self) -> List[Dict]:
        """Scrape event list from weather page"""
        print(f"🌐 Scraping weather events from {self.URL}...")
        
        try:
            resp = self.session.get(self.URL, timeout=30)
            resp.raise_for_status()
        except requests.exceptions.RequestException as e:
            print(f"❌ Failed to fetch weather page: {e}")
            return []
        
        soup = BeautifulSoup(resp.text, 'html.parser')
        links = soup.find_all('a', href=True)
        
        events = []
        seen = set()
        
        for link in links:
            href = link.get('href', '')
            if '/event/' in href:
                slug = href.split('/event/')[1].split('/')[0]
                if slug not in seen:
                    seen.add(slug)
                    text = link.get_text(strip=True)
                    if text and len(text) > 10:
                        events.append({
                            'slug': slug,
                            'title': text,
                            'href': f'https://polymarket.com{href}'
                        })
        
        print(f"✅ Found {len(events)} weather events")
        return events
    
    def get_event_data(self, slug: str) -> Optional[Dict]:
        """Get full event data from event page"""
        url = f'https://polymarket.com/event/{slug}'
        
        try:
            resp = self.session.get(url, timeout=30)
            
            # Extract __NEXT_DATA__
            match = re.search(r'__NEXT_DATA__[^\u003e]*\u003e(.+?)\u003c/script\u003e', resp.text, re.DOTALL)
            if not match:
                return None
            
            data = json.loads(match.group(1))
            queries = data.get('props', {}).get('pageProps', {}).get('dehydratedState', {}).get('queries', [])
            
            for query in queries:
                q_data = query.get('state', {}).get('data', {})
                if isinstance(q_data, dict) and 'markets' in q_data:
                    return q_data
            
            return None
            
        except Exception as e:
            print(f"   ⚠️ Error fetching {slug}: {e}")
            return None
    
    def get_clob_prices(self, condition_id: str) -> Dict:
        """Get prices from CLOB API"""
        if not self.client or not condition_id:
            return {}
        
        try:
            import time
            time.sleep(0.1)  # Rate limit
            
            market = self.client.get_market(condition_id)
            tokens = market.get('tokens', [])
            
            prices = {}
            for token in tokens:
                outcome = token.get('outcome')
                if outcome:
                    prices[outcome] = {
                        'price': token.get('price'),
                        'token_id': token.get('token_id')
                    }
            
            # Only return if we got actual prices
            if prices:
                return prices
            return {}
        except Exception as e:
            print(f"\n      ⚠️ CLOB error for {condition_id[:20]}: {e}")
            return {}
    
    def scrape_full(self) -> List[Dict]:
        """Scrape full market data including CLOB prices"""
        events = self.scrape_events()
        full_markets = []
        
        for i, event in enumerate(events):
            print(f"\n[{i+1}/{len(events)}] Processing: {event['title'][:50]}...")
            
            event_data = self.get_event_data(event['slug'])
            
            if not event_data:
                print("   ⚠️ No event data found")
                continue
            
            # Process markets in this event
            for market in event_data.get('markets', []):
                condition_id = market.get('conditionId')
                
                # Get prices from scraped data (outcomePrices)
                prices = {}
                outcome_prices = market.get('outcomePrices', [])
                outcomes = market.get('outcomes', [])
                
                if outcomes and outcome_prices and len(outcomes) == len(outcome_prices):
                    for i, outcome in enumerate(outcomes):
                        prices[outcome] = {'price': float(outcome_prices[i])}
                    print(f"\n      ✅ Prices: Yes={prices.get('Yes', {}).get('price', 'N/A')} No={prices.get('No', {}).get('price', 'N/A')}")
                elif condition_id and self.client:
                    # Fallback to CLOB API
                    prices = self.get_clob_prices(condition_id)
                
                full_market = {
                    'event_title': event_data.get('title'),
                    'question': market.get('question'),
                    'condition_id': condition_id,
                    'slug': market.get('slug'),
                    'liquidity': market.get('liquidity'),
                    'volume': market.get('volume'),
                    'end_date': event_data.get('endDate'),
                    'resolution_source': event_data.get('resolutionSource'),
                    'prices': prices,
                    'outcomes': market.get('outcomes', [])
                }
                
                full_markets.append(full_market)
                
                # Print summary
                if prices and 'Yes' in prices:
                    print(f"   💰 {market.get('question')[:50]}...")
                    yes_p = prices.get('Yes', {}).get('price', 0)
                    no_p = prices.get('No', {}).get('price', 0)
                    vol = market.get('volumeNum') or market.get('volume') or 0
                    print(f"      Yes: ${yes_p} | No: ${no_p} | Vol: ${vol}")
        
        return full_markets
    
    def save(self, markets: List[Dict], filepath: str = 'data/markets/weather_full.json'):
        """Save to file with timestamp"""
        os.makedirs(os.path.dirname(filepath), exist_ok=True)
        with open(filepath, 'w') as f:
            json.dump(markets, f, indent=2)
        
        # Also save timestamp file for tracking
        timestamp_file = filepath.replace('.json', '.timestamp')
        with open(timestamp_file, 'w') as f:
            f.write(datetime.now().isoformat())
        
        print(f"\n💾 Saved {len(markets)} markets to {filepath}")
        print(f"   Scrape timestamp: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")


def main():
    print(f"\n{'='*60}")
    print(f"🔄 Weather Market Scraper - Started {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print('='*60)
    
    scraper = WeatherMarketScraper()
    markets = scraper.scrape_full()
    
    if markets:
        print("\n" + "=" * 60)
        print(f"📊 TOTAL: {len(markets)} weather markets with full data")
        print("=" * 60)
        scraper.save(markets)
        print("✅ Scrape completed successfully")
        sys.exit(0)
    else:
        print("\n❌ No markets found - scrape failed")
        sys.exit(1)


if __name__ == "__main__":
    main()