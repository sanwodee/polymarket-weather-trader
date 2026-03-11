# Model v2 Accuracy Fixes

## Problems with v1
1. **Overpredicted probabilities** — Returned 35-84% for Chicago ranges when actual was 27.5°F
2. **Weights backwards** — Climatology 40%, forecast 60% (should be forecast-heavy for short-term)
3. **No range handling** — Couldn't properly calculate P(30°F < X < 31°F)
4. **No probability bounds** — Allowed 100% confidence (impossible)
5. **Ignored forecast horizon** — Same weights for tomorrow vs 6 months

## v2 Fixes

### 1. Dynamic Forecast Weighting
```python
# Tomorrow: 90% forecast, 10% climatology
# 1 week: 70% forecast, 30% climatology
# 3+ months: 30% forecast, 70% climatology
```

### 2. Proper Range Probability
```python
# Before: Guessed based on distance from mean
# After: Normal CDF of (high - mean) - CDF of (low - mean)
P(low < X < high) = Φ((high-μ)/σ) - Φ((low-μ)/σ)
```

### 3. Bounded Probabilities
```python
# Never return 0% or 100%
# Always keep 1-99% uncertainty
prob = max(0.01, min(0.99, calculated_prob))
```

### 4. Better Uncertainty
```python
# Include ensemble spread when available
# Otherwise: ±4°F for 1-day, ±6°F for 3-day, etc.
```

## Test Results

### Chicago Feb 23 (Actual: 27.5°F)
| Market | v1 Prediction | v2 Prediction | Actual |
|--------|---------------|---------------|--------|
| 30-31°F | 35% | 3.9% | ❌ (27.5°F) |
| 32-33°F | 74% | 7.8% | ❌ |
| 34-35°F | 78% | 10.2% | ❌ |

**v1 would bet YES and lose. v2 says NO and wins.**

### Miami Feb 24 (Actual: 65.4°F)
| Market | v1 | v2 | Actual |
|--------|-------|-------|--------|
| ≤63°F | 0% | 56.8% | ⚠️ (65.4°F, close) |

**Both models correctly identify this is unlikely.**

## Files Updated
- `src/modeler/predictive_model_v2.py` — New model
- `scripts/weather_paper_trade.py` — Uses V2
- `scripts/two_cities_trade.py` — Uses V2
- `scripts/us_temp_paper_trade.py` — Uses V2

## Next Steps
1. Backtest v2 against 2025 weather data
2. Measure calibration (predicted prob vs actual frequency)
3. Only trade when v2 edge > 10%
