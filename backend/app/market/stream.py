"""
SSE price streaming endpoint.

GET /api/stream/prices streams a Server-Sent Events response; each event is
a JSON object with the latest price data for every tracked ticker.

The client (EventSource) reconnects automatically on drop. The reconnection
delay is communicated via the SSE `retry:` field; the default is
configurable via the STREAM_RETRY_MS environment variable (default 3000 ms).
"""

import asyncio
import json
import os

from fastapi import APIRouter
from fastapi.responses import StreamingResponse

from .interface import PriceCache

router = APIRouter()

# How often (seconds) the server pushes a price update batch
_PUSH_INTERVAL: float = float(os.getenv("STREAM_PUSH_INTERVAL_S", "0.5"))

# Milliseconds the EventSource client should wait before reconnecting
_RETRY_MS: int = int(os.getenv("STREAM_RETRY_MS", "3000"))


async def _price_event_generator(cache: PriceCache):
    """Yield SSE-formatted chunks from the shared PriceCache indefinitely."""
    # Send the retry hint once at connection start
    yield f"retry: {_RETRY_MS}\n\n"

    while True:
        updates = await cache.get_all()
        for update in updates:
            change = update.price - update.previous_price
            change_pct = (change / update.previous_price * 100) if update.previous_price else 0.0
            payload = {
                "ticker": update.ticker,
                "price": round(update.price, 4),
                "previous_price": round(update.previous_price, 4),
                "timestamp": update.timestamp,
                "change": round(change, 4),
                "change_pct": round(change_pct, 4),
                "volume": update.volume,
            }
            yield f"data: {json.dumps(payload)}\n\n"

        await asyncio.sleep(_PUSH_INTERVAL)


def make_stream_router(cache: PriceCache) -> APIRouter:
    """
    Return an APIRouter with the SSE endpoint wired to *cache*.

    This factory pattern lets the app inject the shared PriceCache instance
    without relying on global state inside this module.
    """

    @router.get("/api/stream/prices", summary="SSE price stream")
    async def stream_prices():
        return StreamingResponse(
            _price_event_generator(cache),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "X-Accel-Buffering": "no",
                "Connection": "keep-alive",
            },
        )

    return router
