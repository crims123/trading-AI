# Market Interface Design

Unified Python abstraction layer for market data retrieval, supporting both real Massive API and built-in simulator.

## Architecture Overview

The market data layer follows a strategy pattern:

```
┌─────────────────────────────────────────┐
│  FastAPI Background Task (price polling) │
└─────────────────┬───────────────────────┘
                  │
         ┌────────▼─────────┐
         │ MarketDataSource │ (Abstract Base Class)
         └────────┬─────────┘
                  │
      ┌───────────┴──────────────┐
      │                          │
  ┌───▼────────┐         ┌───────▼──────┐
  │ Simulator  │         │ Massive API  │
  │ (default)  │         │ (if key set) │
  └───┬────────┘         └───────┬──────┘
      │                          │
      └───────────┬──────────────┘
                  │
         ┌────────▼──────────┐
         │  Price Cache      │ (in-memory)
         └────────┬──────────┘
                  │
         ┌────────▼──────────┐
         │  SSE Stream       │ (frontend)
         └───────────────────┘
```

## Core Data Structures

### PriceUpdate

Represents a single price tick for a ticker.

```python
from dataclasses import dataclass
from datetime import datetime

@dataclass
class PriceUpdate:
    """A single price update for a ticker."""
    ticker: str
    price: float          # Current price
    previous_price: float # Previous price (for % change calculation)
    timestamp: int        # Unix milliseconds
    volume: int           # Optional trading volume
    high: float | None = None
    low: float | None = None
```

### PriceCache

In-memory cache of latest prices for all known tickers.

```python
from typing import Dict

class PriceCache:
    """Thread-safe in-memory price cache."""
    
    def __init__(self):
        self._prices: Dict[str, PriceUpdate] = {}
        self._lock = asyncio.Lock()
    
    async def update(self, update: PriceUpdate) -> None:
        """Store or update a price."""
        async with self._lock:
            self._prices[update.ticker] = update
    
    async def update_batch(self, updates: list[PriceUpdate]) -> None:
        """Efficiently batch-update multiple prices."""
        async with self._lock:
            for update in updates:
                self._prices[update.ticker] = update
    
    async def get(self, ticker: str) -> PriceUpdate | None:
        """Retrieve latest price for a ticker."""
        async with self._lock:
            return self._prices.get(ticker)
    
    async def get_all(self) -> list[PriceUpdate]:
        """Get all cached prices."""
        async with self._lock:
            return list(self._prices.values())
```

## Abstract Market Data Source

```python
from abc import ABC, abstractmethod
from typing import Optional

class MarketDataSource(ABC):
    """Abstract base class for all market data sources."""
    
    @abstractmethod
    async def initialize(self) -> None:
        """One-time initialization (e.g., load seed data)."""
        pass
    
    @abstractmethod
    async def get_current_prices(
        self, 
        tickers: list[str]
    ) -> list[PriceUpdate]:
        """
        Fetch current prices for a list of tickers.
        
        Args:
            tickers: List of ticker symbols (e.g., ["AAPL", "GOOGL"])
        
        Returns:
            List of PriceUpdate objects. May be partial if some tickers fail.
        
        Raises:
            MarketDataError: If the entire request fails (connection, auth, etc.)
        """
        pass
    
    async def shutdown(self) -> None:
        """Cleanup (e.g., close connections). Optional override."""
        pass
```

## Implementation: Massive API Client

```python
import os
from massive import RESTClient
from massive.rest.models import SnapshotMarketType
from massive.rest.exceptions import APIError

class MassiveDataSource(MarketDataSource):
    """Real market data via Massive API."""
    
    def __init__(self):
        self.client = RESTClient(api_key=os.getenv("MASSIVE_API_KEY"))
    
    async def initialize(self) -> None:
        # Massive API doesn't require warmup
        pass
    
    async def get_current_prices(
        self, 
        tickers: list[str]
    ) -> list[PriceUpdate]:
        """
        Fetch prices from Massive API snapshot endpoint.
        Uses bulk endpoint for efficiency: one call for all tickers.
        """
        if not tickers:
            return []
        
        try:
            # Single API call for all tickers
            tickers_str = ",".join(tickers)
            snapshots = self.client.get_snapshot_all(
                market_type=SnapshotMarketType.STOCKS,
                tickers=tickers
            )
            
            updates = []
            for snap in snapshots:
                if snap.day and snap.prev_day:
                    update = PriceUpdate(
                        ticker=snap.ticker,
                        price=snap.day.close,
                        previous_price=snap.prev_day.close,
                        timestamp=snap.updated,
                        volume=snap.day.volume,
                        high=snap.day.high,
                        low=snap.day.low,
                    )
                    updates.append(update)
            
            return updates
            
        except APIError as e:
            if e.status_code == 401:
                raise MarketDataError(f"Invalid Massive API key: {e}")
            elif e.status_code == 429:
                raise MarketDataError(f"Massive API rate limit exceeded: {e}")
            else:
                raise MarketDataError(f"Massive API error: {e}")
        except Exception as e:
            raise MarketDataError(f"Failed to fetch prices from Massive: {e}")
```

## Factory Function

The entry point for creating the appropriate market data source based on environment variables.

```python
import os

def create_market_data_source() -> MarketDataSource:
    """
    Factory function that selects the market data source.
    
    Returns:
        MassiveDataSource if MASSIVE_API_KEY is set and non-empty.
        SimulatorDataSource otherwise (default).
    """
    api_key = os.getenv("MASSIVE_API_KEY", "").strip()
    
    if api_key:
        print("Using Massive API for real market data")
        return MassiveDataSource()
    else:
        print("Using built-in market simulator")
        return SimulatorDataSource()
```

## Polling Background Task

This runs in the FastAPI lifespan to continuously fetch and cache prices.

```python
import asyncio
from fastapi import FastAPI

app = FastAPI()

# Shared global state
market_source: MarketDataSource
price_cache: PriceCache
watchlist_tickers: list[str] = []

async def poll_prices_task():
    """
    Background task: continuously poll market data and update cache.
    Runs every 500ms (configurable).
    """
    poll_interval = 0.5  # seconds
    
    while True:
        try:
            if watchlist_tickers:
                updates = await market_source.get_current_prices(watchlist_tickers)
                await price_cache.update_batch(updates)
        except MarketDataError as e:
            # Log and continue (don't crash the app)
            print(f"Price polling error: {e}")
        except Exception as e:
            # Unexpected error — log and backoff
            print(f"Unexpected error in price polling: {e}")
            await asyncio.sleep(2)  # Backoff
        
        await asyncio.sleep(poll_interval)

@app.lifespan
async def lifespan(app: FastAPI):
    # Startup
    global market_source, price_cache
    market_source = create_market_data_source()
    price_cache = PriceCache()
    
    await market_source.initialize()
    
    # Start background polling task
    polling_task = asyncio.create_task(poll_prices_task())
    
    yield
    
    # Shutdown
    polling_task.cancel()
    try:
        await polling_task
    except asyncio.CancelledError:
        pass
    
    await market_source.shutdown()
```

## Integration with Watchlist

When the user adds/removes tickers from their watchlist, the polling task automatically updates its targets.

```python
@app.post("/api/watchlist")
async def add_ticker(request: AddTickerRequest):
    """Add a ticker to the user's watchlist."""
    global watchlist_tickers
    
    ticker = request.ticker.upper()
    
    # Add to watchlist in database
    db.insert_watchlist(ticker)
    
    # Update polling targets
    if ticker not in watchlist_tickers:
        watchlist_tickers.append(ticker)
    
    # Trigger an immediate price fetch for this ticker
    try:
        updates = await market_source.get_current_prices([ticker])
        await price_cache.update_batch(updates)
    except MarketDataError:
        pass  # Graceful: price will fetch in next polling cycle
    
    return {"status": "ok", "ticker": ticker}
```

## Error Handling

```python
class MarketDataError(Exception):
    """Base exception for market data layer errors."""
    pass

class RateLimitError(MarketDataError):
    """Raised when API rate limit is exceeded."""
    pass

class InvalidTickerError(MarketDataError):
    """Raised when a ticker is not found."""
    pass
```

## Environment Variable Contract

- **`MASSIVE_API_KEY`**: If set and non-empty, use Massive API. Otherwise, use simulator.
- **No other configuration needed**: The interface abstracts all details.

## Testing Strategy

### Mock Market Data Source

```python
class MockDataSource(MarketDataSource):
    """For unit and integration tests."""
    
    def __init__(self, seed_prices: dict[str, float]):
        self.seed_prices = seed_prices
        self.call_count = 0
    
    async def initialize(self):
        pass
    
    async def get_current_prices(self, tickers: list[str]) -> list[PriceUpdate]:
        self.call_count += 1
        updates = []
        for ticker in tickers:
            if ticker in self.seed_prices:
                price = self.seed_prices[ticker]
                updates.append(PriceUpdate(
                    ticker=ticker,
                    price=price,
                    previous_price=price * 0.99,
                    timestamp=int(time.time() * 1000),
                ))
        return updates
```

## References

- See `MARKET_SIMULATOR.md` for simulator implementation
- See `MASSIVE_API.md` for API endpoint details
