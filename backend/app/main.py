"""
FinAlly backend — FastAPI application entry point.

Responsibilities wired here:
  - Load environment variables from the project-root .env file
  - Initialise the market data source (simulator or Massive API)
  - Run the background price-polling task
  - Expose /api/stream/prices (SSE) and /api/health
  - Serve the compiled Next.js static export from /static
"""

import asyncio
import os
from contextlib import asynccontextmanager
from pathlib import Path

from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

# Load .env from repo root (one level above backend/)
load_dotenv(Path(__file__).resolve().parents[2] / ".env")

from app.market.factory import create_market_data_source  # noqa: E402
from app.market.interface import PriceCache  # noqa: E402
from app.market.stream import make_stream_router  # noqa: E402

# ---------------------------------------------------------------------------
# Global shared state (populated during lifespan startup)
# ---------------------------------------------------------------------------
price_cache = PriceCache()
market_source = None
_watchlist_tickers: list[str] = []

# Configurable poll interval (seconds); default 500 ms
_POLL_INTERVAL: float = float(os.getenv("POLL_INTERVAL_S", "0.5"))


async def _poll_prices() -> None:
    """Background task: fetch prices and write them to the cache continuously."""
    while True:
        try:
            if _watchlist_tickers and market_source is not None:
                updates = await market_source.get_current_prices(_watchlist_tickers)
                await price_cache.update_batch(updates)
        except Exception as exc:
            # Log and back off; don't crash the app
            print(f"[poll] Price fetch error: {exc}")
            await asyncio.sleep(2)
            continue

        await asyncio.sleep(_POLL_INTERVAL)


@asynccontextmanager
async def lifespan(app: FastAPI):
    global market_source, _watchlist_tickers

    market_source = create_market_data_source()
    await market_source.initialize()

    # Default watchlist from the DB seed — duplicated here so the poller
    # starts immediately without waiting for a DB query.
    _watchlist_tickers = [
        "AAPL", "GOOGL", "MSFT", "AMZN", "TSLA",
        "NVDA", "META", "JPM", "V", "NFLX",
    ]

    polling_task = asyncio.create_task(_poll_prices())

    yield

    polling_task.cancel()
    try:
        await polling_task
    except asyncio.CancelledError:
        pass

    await market_source.shutdown()


app = FastAPI(title="FinAlly Backend", lifespan=lifespan)

# SSE streaming
app.include_router(make_stream_router(price_cache))


@app.get("/api/health")
async def health():
    return {"status": "ok"}


# Serve static Next.js export if the build directory exists
_static_dir = Path(__file__).parent / "static"
if _static_dir.is_dir():
    app.mount("/", StaticFiles(directory=str(_static_dir), html=True), name="static")
