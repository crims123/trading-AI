"""
Unit tests for app.market.interface — PriceUpdate, PriceCache, and exceptions.
"""

import asyncio
import time

import pytest

from app.market.interface import (
    InvalidTickerError,
    MarketDataError,
    PriceCache,
    PriceUpdate,
    RateLimitError,
)


# ---------------------------------------------------------------------------
# PriceUpdate
# ---------------------------------------------------------------------------


def test_price_update_required_fields():
    ts = int(time.time() * 1000)
    u = PriceUpdate(ticker="AAPL", price=190.0, previous_price=188.0, timestamp=ts)
    assert u.ticker == "AAPL"
    assert u.price == 190.0
    assert u.previous_price == 188.0
    assert u.timestamp == ts
    assert u.volume == 0
    assert u.high is None
    assert u.low is None


def test_price_update_optional_fields():
    ts = int(time.time() * 1000)
    u = PriceUpdate(
        ticker="TSLA",
        price=245.0,
        previous_price=240.0,
        timestamp=ts,
        volume=5_000_000,
        high=250.0,
        low=238.0,
    )
    assert u.volume == 5_000_000
    assert u.high == 250.0
    assert u.low == 238.0


# ---------------------------------------------------------------------------
# PriceCache
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_cache_starts_empty():
    cache = PriceCache()
    assert await cache.get_all() == []


@pytest.mark.asyncio
async def test_cache_update_single():
    cache = PriceCache()
    ts = int(time.time() * 1000)
    update = PriceUpdate("AAPL", 190.0, 188.0, ts)
    await cache.update(update)

    result = await cache.get("AAPL")
    assert result is not None
    assert result.price == 190.0


@pytest.mark.asyncio
async def test_cache_update_replaces_previous():
    cache = PriceCache()
    ts = int(time.time() * 1000)
    await cache.update(PriceUpdate("AAPL", 190.0, 188.0, ts))
    await cache.update(PriceUpdate("AAPL", 195.0, 190.0, ts + 500))

    result = await cache.get("AAPL")
    assert result.price == 195.0


@pytest.mark.asyncio
async def test_cache_get_unknown_ticker_returns_none():
    cache = PriceCache()
    result = await cache.get("UNKNOWN")
    assert result is None


@pytest.mark.asyncio
async def test_cache_update_batch():
    cache = PriceCache()
    ts = int(time.time() * 1000)
    updates = [
        PriceUpdate("AAPL", 190.0, 188.0, ts),
        PriceUpdate("GOOGL", 175.0, 172.0, ts),
        PriceUpdate("MSFT", 422.0, 420.0, ts),
    ]
    await cache.update_batch(updates)

    all_prices = await cache.get_all()
    tickers = {p.ticker for p in all_prices}
    assert tickers == {"AAPL", "GOOGL", "MSFT"}


@pytest.mark.asyncio
async def test_cache_get_all_returns_snapshot():
    cache = PriceCache()
    ts = int(time.time() * 1000)
    await cache.update(PriceUpdate("AAPL", 190.0, 188.0, ts))
    await cache.update(PriceUpdate("GOOGL", 175.0, 172.0, ts))

    snapshot = await cache.get_all()
    assert len(snapshot) == 2


@pytest.mark.asyncio
async def test_cache_clear():
    cache = PriceCache()
    ts = int(time.time() * 1000)
    await cache.update(PriceUpdate("AAPL", 190.0, 188.0, ts))
    await cache.clear()
    assert await cache.get_all() == []


@pytest.mark.asyncio
async def test_cache_concurrent_updates_are_safe():
    """Multiple coroutines updating the cache concurrently should not corrupt state."""
    cache = PriceCache()
    ts = int(time.time() * 1000)

    async def updater(ticker: str, price: float):
        for i in range(20):
            await cache.update(PriceUpdate(ticker, price + i, price + i - 1, ts + i))

    await asyncio.gather(
        updater("AAPL", 190.0),
        updater("GOOGL", 175.0),
        updater("MSFT", 422.0),
    )

    all_prices = await cache.get_all()
    assert len(all_prices) == 3  # exactly one entry per ticker


# ---------------------------------------------------------------------------
# Exceptions
# ---------------------------------------------------------------------------


def test_market_data_error_is_exception():
    with pytest.raises(MarketDataError):
        raise MarketDataError("test")


def test_rate_limit_error_is_market_data_error():
    with pytest.raises(MarketDataError):
        raise RateLimitError("rate limited")


def test_invalid_ticker_error_is_market_data_error():
    with pytest.raises(MarketDataError):
        raise InvalidTickerError("bad ticker")
