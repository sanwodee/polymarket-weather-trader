#!/usr/bin/env python3
import sys
sys.path.insert(0, 'src')
from gatherer.sources.openmeteo import OpenMeteoGatherer
import os

# Clear cache
for f in ['data/weather/32.7800_-96.8000_2026-02-24.json']:
    if os.path.exists(f):
        os.remove(f)
        print(f'Cleared {f}')

# Test
gatherer = OpenMeteoGatherer()
result = gatherer.get_forecast(32.78, -96.80, '2026-02-24')

print(f'\n✅ Source: {result.get("source", "unknown")}')
print(f'✅ Temp max: {result.get("temp_max")}°F')
print(f'✅ Temp min: {result.get("temp_min")}°F')
print(f'✅ Temp mean: {result.get("temp_mean")}°F')
print(f'✅ Date: {result.get("date")}')

if 'error' in result:
    print(f'\n❌ Error: {result["error"]}')
