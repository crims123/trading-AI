# Massive API Documentation

Research and integration guide for the Massive API (formerly Polygon.io), covering real-time and end-of-day stock price retrieval.

## Overview

Massive provides market data through REST and WebSocket APIs. For FinAlly, we use the REST API for polling-based market data retrieval, which is simpler and more reliable than WebSocket for a single-user application.

## Key Endpoints

### 1. Multi-Ticker Snapshot (Bulk Real-time Data)

**Endpoint**: `GET /api/v1/stocks/snapshot`

**Purpose**: Fetch current price snapshot for multiple tickers in a single request.

**Query Parameters**:
- `tickers` (string): Comma-separated list of ticker symbols (e.g., `AAPL,GOOGL,MSFT`)

**Response**:
```json
{
  "data": [
    {
      "ticker": "AAPL",
      "todaysChange": 1.50,
      "todaysChangePerc": 0.80,
      "updated": 1605192895000000000
    },
    {
      "ticker": "GOOGL",
      "todaysChange": -2.25,
      "todaysChangePerc": -1.15,
      "updated": 1605192894000000000
    }
  ]
}
```

**Pros**:
- Single API call for all tickers
- Lightweight response
- Fast polling interval (~500ms feasible)

**Cons**:
- Missing close price (only `todaysChange` and percentage)
- No OHLC data
- Need separate endpoint for full price data

### 2. Single Ticker Snapshot (Detailed Real-time)

**Endpoint**: `GET /v2/snapshot/locale/us/markets/stocks/tickers/{ticker}`

**Purpose**: Full market snapshot for one ticker including last trade, last quote, minute bar, and daily bar.

**Response**:
```json
{
  "status": "OK",
  "ticker": {
    "ticker": "AAPL",
    "day": {
      "c": 120.4229,
      "h": 120.53,
      "l": 118.81,
      "o": 119.62,
      "v": 28727868,
      "vw": 119.725
    },
    "lastTrade": {
      "p": 120.47,
      "s": 236,
      "t": 1605195918306274000
    },
    "lastQuote": {
      "p": 120.46,
      "s": 8,
      "t": 1605195918507251700
    },
    "min": {
      "c": 120.4201,
      "o": 120.435,
      "h": 120.468,
      "l": 120.37,
      "v": 270796
    },
    "prevDay": {
      "c": 119.49,
      "h": 119.63,
      "l": 116.44,
      "o": 117.19,
      "v": 110597265
    },
    "todaysChange": 0.98,
    "todaysChangePerc": 0.82,
    "updated": 1605195918306274000
  }
}
```

**Pros**:
- Complete OHLC data (day and previous day)
- Last trade and quote information
- Perfect for detailed analysis

**Cons**:
- One API call per ticker (high quota usage)
- Not suitable for polling 10+ tickers every 500ms

### 3. Previous Day Bar (EOD Data)

**Endpoint**: `GET /v2/aggs/ticker/{ticker}/prev`

**Purpose**: Get the previous trading day's OHLC data.

**Response**:
```json
{
  "status": "OK",
  "ticker": "AAPL",
  "results": [
    {
      "c": 115.97,
      "h": 117.59,
      "l": 114.13,
      "o": 115.55,
      "v": 131704427,
      "vw": 116.3058,
      "t": 1605042000000
    }
  ]
}
```

**Use Case**: Initialize position cost basis, historical reference.

### 4. Daily Open/Close (Specific Date)

**Endpoint**: `GET /v1/open-close/{ticker}/{date}`

**Purpose**: Get OHLC for a specific date (YYYY-MM-DD format).

**Response**:
```json
{
  "status": "OK",
  "symbol": "AAPL",
  "from": "2023-01-09",
  "open": 324.66,
  "high": 326.2,
  "low": 322.3,
  "close": 325.12,
  "volume": 26122646,
  "afterHours": 322.1,
  "preMarket": 324.5
}
```

**Use Case**: Portfolio seed data, historical analysis.

## Python Client Library

The official Massive Python client wraps these REST endpoints with convenient methods.

### Installation

```bash
pip install massive
# or with uv:
uv add massive
```

### Basic Usage

```python
from massive import RESTClient
from massive.rest.models import SnapshotMarketType

# Initialize client (auto-loads MASSIVE_API_KEY env var)
client = RESTClient()

# Get snapshots for multiple tickers
snapshots = client.get_snapshot_all(
    market_type=SnapshotMarketType.STOCKS,
    tickers=["AAPL", "GOOGL", "MSFT"]
)

for snap in snapshots:
    print(f"{snap.ticker}: ${snap.day.close:.2f}, Change: {snap.todays_change_perc:.2f}%")

# Get single ticker detailed snapshot
aapl_snap = client.get_snapshot_ticker(
    market_type=SnapshotMarketType.STOCKS,
    ticker="AAPL"
)
print(f"AAPL: ${aapl_snap.day.close:.2f}")
print(f"  High: ${aapl_snap.day.high:.2f}, Low: ${aapl_snap.day.low:.2f}")
print(f"  Volume: {aapl_snap.day.volume:,}")
```

### Polling Loop Example

```python
import time
from massive import RESTClient
from massive.rest.models import SnapshotMarketType

client = RESTClient()
tickers = ["AAPL", "GOOGL", "MSFT", "AMZN", "TSLA"]

while True:
    try:
        snapshots = client.get_snapshot_all(
            market_type=SnapshotMarketType.STOCKS,
            tickers=tickers
        )
        
        for snap in snapshots:
            # Extract current price (use day.close or lastTrade.p)
            current_price = snap.day.close if snap.day else None
            previous_price = snap.prev_day.close if snap.prev_day else None
            
            if current_price and previous_price:
                change_pct = ((current_price - previous_price) / previous_price) * 100
                direction = "↑" if change_pct > 0 else "↓"
                print(f"{snap.ticker}: ${current_price:.2f} {direction} {change_pct:.2f}%")
        
        time.sleep(0.5)  # Poll every 500ms
        
    except Exception as e:
        print(f"Error fetching prices: {e}")
        time.sleep(2)  # Backoff on error
```

## Rate Limits & Tier Considerations

- **Starter Tier**: Limited concurrent requests and lower rate limits
- **Recommendation**: Use the bulk snapshot endpoint (`/api/v1/stocks/snapshot`) to minimize API calls
- **Polling Strategy**: For 10 tickers at 500ms intervals, use one call to bulk snapshot instead of 10 individual calls

## Integration Points

1. **Environment Variable**: `MASSIVE_API_KEY` in `.env` enables Massive client
2. **Fallback**: If `MASSIVE_API_KEY` is not set or empty, use built-in simulator
3. **Price Cache**: Integrate polling results into the in-memory price cache (see `MARKET_INTERFACE.md`)
4. **SSE Stream**: Polled data feeds the SSE price stream to the frontend

## Error Handling

```python
from massive.rest.exceptions import APIError

try:
    snapshots = client.get_snapshot_all(
        market_type=SnapshotMarketType.STOCKS,
        tickers=["AAPL", "INVALID"]
    )
except APIError as e:
    if e.status_code == 401:
        print("Invalid API key")
    elif e.status_code == 429:
        print("Rate limit exceeded, backing off")
    else:
        print(f"API error: {e}")
```

## Testing Strategy

- Mock `RESTClient` in unit tests
- Use `LLM_MOCK=false` and `MASSIVE_API_KEY=""` to test simulator path
- E2E tests with `docker-compose.test.yml` can use a limited Massive API key or mock responses

## References

- Official Massive Docs: https://massive.com/docs/
- Python Client GitHub: https://github.com/massive-com/client-python
