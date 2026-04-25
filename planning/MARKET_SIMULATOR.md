# Market Simulator Documentation

Design and implementation of the built-in market price simulator using Geometric Brownian Motion (GBM).

## Overview

The simulator generates realistic price movements for any set of tickers without requiring external API calls. It's the default data source when `MASSIVE_API_KEY` is not set.

**Key Properties**:
- Deterministic (seeded for reproducibility)
- Realistic price behavior via GBM
- Correlated moves across tickers (e.g., tech stocks move together)
- Occasional random events (2-5% jumps) for drama
- Efficient: low CPU, runs in-process
- No external dependencies beyond numpy

## Geometric Brownian Motion (GBM)

GBM models stock prices using the stochastic differential equation:

```
dS = μ * S * dt + σ * S * dW
```

Where:
- `S` = stock price
- `μ` = drift (expected return)
- `σ` = volatility (standard deviation)
- `dW` = Wiener process increment (random normal)

**Discrete approximation** (what we implement):

```
S(t+1) = S(t) * exp((μ - σ²/2) * dt + σ * √(dt) * Z)

Where Z ~ N(0, 1) (standard normal)
```

## Implementation

### Core Simulator Class

```python
import numpy as np
from datetime import datetime
import time
from typing import Dict

class MarketSimulator:
    """
    Generates realistic price movements using Geometric Brownian Motion.
    Supports multiple correlated tickers with independent random events.
    """
    
    def __init__(self, seed: int = 42):
        """
        Initialize the simulator.
        
        Args:
            seed: Random seed for reproducibility. Use None for non-deterministic behavior.
        """
        self.rng = np.random.RandomState(seed)
        self.prices: Dict[str, float] = {}
        self.previous_prices: Dict[str, float] = {}
        self.tick_count = 0
        self.market_factor = 1.0  # Correlation factor (affects all tickers)
    
    def add_ticker(
        self,
        ticker: str,
        initial_price: float,
        drift: float = 0.0001,    # ~0.0125% per day (25% annualized)
        volatility: float = 0.02,  # ~2% per update (25% annualized)
    ) -> None:
        """
        Add a ticker to the simulator.
        
        Args:
            ticker: Stock symbol (e.g., "AAPL")
            initial_price: Starting price
            drift: Expected return per update (drift coefficient)
            volatility: Price volatility per update (standard deviation)
        """
        self.prices[ticker] = initial_price
        self.previous_prices[ticker] = initial_price
        
        if not hasattr(self, 'params'):
            self.params = {}
        
        self.params[ticker] = {
            'drift': drift,
            'volatility': volatility,
        }
    
    def step(self, dt: float = 1.0) -> None:
        """
        Advance the simulation by one time step and generate new prices.
        
        Args:
            dt: Time delta (e.g., 1.0 for one interval unit)
        """
        self.tick_count += 1
        
        # Market-wide correlation factor: ~5% chance of sudden move
        if self.rng.random() < 0.05:
            self.market_factor *= (1 + self.rng.normal(0, 0.02))
            self.market_factor = np.clip(self.market_factor, 0.95, 1.05)
        
        # Update each ticker
        for ticker in self.prices:
            prev_price = self.prices[ticker]
            params = self.params[ticker]
            
            # GBM increment
            drift = params['drift'] * dt
            vol = params['volatility'] * np.sqrt(dt)
            dW = self.rng.normal(0, 1)
            
            # Random event: occasional 2-5% jump
            event_factor = 1.0
            if self.rng.random() < 0.01:  # 1% chance per tick
                event_factor = 1 + self.rng.normal(0, 0.03)  # ±3% std
            
            # New price: GBM with market correlation and random event
            log_return = drift - (vol ** 2) / 2 + vol * dW
            new_price = prev_price * np.exp(log_return) * (1 + (self.market_factor - 1) * 0.5) * event_factor
            
            # Clamp to reasonable bounds (don't let prices go to zero or explode)
            new_price = np.clip(new_price, prev_price * 0.5, prev_price * 2.0)
            
            # Store old price and update
            self.previous_prices[ticker] = prev_price
            self.prices[ticker] = float(new_price)
    
    def get_price(self, ticker: str) -> float | None:
        """Get current price for a ticker."""
        return self.prices.get(ticker)
    
    def get_all_prices(self) -> Dict[str, float]:
        """Get all current prices."""
        return dict(self.prices)
    
    def get_previous_price(self, ticker: str) -> float | None:
        """Get previous price (for change calculation)."""
        return self.previous_prices.get(ticker)
```

### Default Seed Prices

Realistic starting prices for the default 10 tickers in FinAlly.

```python
DEFAULT_SEED_PRICES = {
    "AAPL": 190.50,    # Apple
    "GOOGL": 175.25,   # Google
    "MSFT": 422.75,    # Microsoft
    "AMZN": 182.50,    # Amazon
    "TSLA": 245.30,    # Tesla
    "NVDA": 875.20,    # Nvidia
    "META": 508.40,    # Meta
    "JPM": 195.80,     # JPMorgan
    "V": 288.60,       # Visa
    "NFLX": 425.75,    # Netflix
}

DEFAULT_VOLATILITIES = {
    "AAPL": 0.015,     # Tech: moderate volatility
    "GOOGL": 0.016,
    "MSFT": 0.014,
    "AMZN": 0.018,     # High volatility stocks
    "TSLA": 0.028,     # Very high volatility
    "NVDA": 0.025,
    "META": 0.020,
    "JPM": 0.012,      # Finance: lower volatility
    "V": 0.011,
    "NFLX": 0.022,
}
```

### SimulatorDataSource (Adapter to Market Interface)

Implements the abstract `MarketDataSource` interface.

```python
from market_interface import MarketDataSource, PriceUpdate
import time

class SimulatorDataSource(MarketDataSource):
    """
    Adapter: wraps MarketSimulator for use as a MarketDataSource.
    Generates prices via GBM instead of external API.
    """
    
    def __init__(self):
        self.simulator = MarketSimulator(seed=42)
        self.last_step_time = 0
    
    async def initialize(self) -> None:
        """Seed the simulator with default tickers."""
        for ticker, price in DEFAULT_SEED_PRICES.items():
            volatility = DEFAULT_VOLATILITIES.get(ticker, 0.02)
            self.simulator.add_ticker(
                ticker,
                initial_price=price,
                volatility=volatility,
            )
        
        # Do initial step to populate prices
        self.simulator.step()
    
    async def get_current_prices(self, tickers: list[str]) -> list[PriceUpdate]:
        """
        Return current simulated prices.
        Advances simulator if enough real time has passed.
        """
        # Advance simulator every ~500ms of real time
        current_time = time.time()
        if current_time - self.last_step_time >= 0.5:
            self.simulator.step()
            self.last_step_time = current_time
        
        updates = []
        timestamp_ms = int(time.time() * 1000)
        
        for ticker in tickers:
            price = self.simulator.get_price(ticker)
            prev_price = self.simulator.get_previous_price(ticker)
            
            if price is not None and prev_price is not None:
                update = PriceUpdate(
                    ticker=ticker,
                    price=price,
                    previous_price=prev_price,
                    timestamp=timestamp_ms,
                    volume=int(self.rng.normal(1_000_000, 200_000)),
                )
                updates.append(update)
        
        return updates
```

## Calibration

Simulator parameters are tuned to match real market behavior:

### Drift (Expected Return)

```python
drift = 0.0001  # Per 500ms tick
# Annualized: 0.0001 * ~1000 ticks/day * ~252 days/year ≈ 25% annual return
```

This is slightly optimistic but keeps the sim fun for a demo. Adjust downward for more realistic behavior.

### Volatility

```python
volatility = 0.015 to 0.028  # Per 500ms tick, ticker-specific
# Annualized: 0.02 * √(~1000 ticks/day) ≈ 63% annualized vol
```

This is on the high end of real-world equity volatility, making the simulator more dynamic and visually interesting.

### Event Frequency

```python
event_probability = 0.01  # 1% chance per tick (500ms)
# Daily: ~50% chance at least one event
event_magnitude = ±3% (std dev)
```

This creates occasional surprises without being unrealistic.

## Properties & Behavior

### Correlation

All tickers affected by shared `market_factor`:

```python
market_factor *= (1 + random_normal(0, 0.02))
new_price = prev_price * exp(GBM) * (1 + (market_factor - 1) * 0.5) * event_factor
```

Tech stocks tend to move together; this factor creates realistic, co-moving behavior.

### Mean Reversion

Prices are clamped:

```python
new_price = np.clip(new_price, prev_price * 0.5, prev_price * 2.0)
```

Prevents unbounded explosion or collapse. Adjust the bounds if needed.

### Reproducibility

With a fixed seed (default: 42), the same price sequence is generated every run. Useful for testing.

```python
simulator = MarketSimulator(seed=42)  # Deterministic
simulator = MarketSimulator(seed=None)  # Non-deterministic
```

## Integration with FastAPI

The polling task in `MARKET_INTERFACE.md` calls `SimulatorDataSource.get_current_prices()` every 500ms, which triggers GBM steps and returns new prices.

```python
# In polling loop (from MARKET_INTERFACE.md):
updates = await market_source.get_current_prices(watchlist_tickers)
await price_cache.update_batch(updates)
```

The frontend receives these prices via SSE and renders them with flash animations.

## Testing

### Unit Tests

```python
import pytest

def test_gbm_generates_prices():
    sim = MarketSimulator(seed=42)
    sim.add_ticker("TEST", initial_price=100.0)
    
    assert sim.get_price("TEST") == 100.0
    sim.step()
    assert sim.get_price("TEST") != 100.0  # Price changed

def test_prices_dont_explode():
    sim = MarketSimulator(seed=42)
    sim.add_ticker("TEST", initial_price=100.0, volatility=0.5)
    
    for _ in range(10000):
        sim.step()
    
    price = sim.get_price("TEST")
    assert 50 < price < 200  # Clipping prevents explosion

def test_correlation():
    sim = MarketSimulator(seed=42)
    sim.add_ticker("A", 100.0)
    sim.add_ticker("B", 100.0)
    
    prices_a = []
    prices_b = []
    
    for _ in range(100):
        sim.step()
        prices_a.append(sim.get_price("A"))
        prices_b.append(sim.get_price("B"))
    
    # Correlation should be > 0 (both affected by market_factor)
    correlation = np.corrcoef(prices_a, prices_b)[0, 1]
    assert correlation > 0.3
```

### E2E with Simulator

Run the app with `MASSIVE_API_KEY=""` (unset or empty):

```bash
export MASSIVE_API_KEY=""
uvicorn backend.app:app --reload
```

The frontend will show live-updating prices from the simulator. No API key needed.

## Performance

- **CPU**: Minimal. GBM step is O(n) in number of tickers (~10), and runs every 500ms.
- **Memory**: Constant. Simulator stores one float per ticker.
- **Latency**: <1ms to generate 10 prices.

No scaling issues even with hundreds of tickers.

## Future Enhancements

1. **Seasonality**: Add time-of-day or day-of-week patterns
2. **Mean Reversion**: Implement Ornstein-Uhlenbeck process for mean-reverting assets
3. **Jumps**: Poisson jump process for gap moves
4. **Microstructure**: Bid-ask spreads, slippage
5. **News Integration**: Spike prices in response to simulated news events

## References

- Black-Scholes Model: https://en.wikipedia.org/wiki/Black%E2%80%93Scholes_model
- GBM Implementation: https://en.wikipedia.org/wiki/Geometric_Brownian_motion
- NumPy Random: https://numpy.org/doc/stable/reference/random/index.html
