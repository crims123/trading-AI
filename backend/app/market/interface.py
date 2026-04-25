"""
Abstract market data interface: shared types, cache, and base class.

All market data sources (simulator, Massive API) implement MarketDataSource.
The PriceCache holds the latest tick for every known ticker in memory.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
import asyncio
from typing import Dict, Optional


@dataclass
class PriceUpdate:
    """A single price tick for one ticker."""

    ticker: str
    price: float
    previous_price: float
    timestamp: int  # Unix milliseconds
    volume: int = 0
    high: Optional[float] = None
    low: Optional[float] = None


class MarketDataError(Exception):
    """Base exception for market data layer errors."""


class RateLimitError(MarketDataError):
    """Raised when the upstream API rate limit is exceeded."""


class InvalidTickerError(MarketDataError):
    """Raised when a requested ticker is not found."""


class PriceCache:
    """Thread-safe in-memory store of the latest price for every tracked ticker."""

    def __init__(self) -> None:
        self._prices: Dict[str, PriceUpdate] = {}
        self._lock = asyncio.Lock()

    async def update(self, update: PriceUpdate) -> None:
        """Store or replace the latest price for a single ticker."""
        async with self._lock:
            self._prices[update.ticker] = update

    async def update_batch(self, updates: list[PriceUpdate]) -> None:
        """Atomically update multiple tickers at once."""
        async with self._lock:
            for update in updates:
                self._prices[update.ticker] = update

    async def get(self, ticker: str) -> Optional[PriceUpdate]:
        """Return the latest cached price for *ticker*, or None if unknown."""
        async with self._lock:
            return self._prices.get(ticker)

    async def get_all(self) -> list[PriceUpdate]:
        """Return a snapshot of all currently cached prices."""
        async with self._lock:
            return list(self._prices.values())

    async def clear(self) -> None:
        """Remove all cached prices (used in tests)."""
        async with self._lock:
            self._prices.clear()


class MarketDataSource(ABC):
    """Strategy interface for market data providers."""

    @abstractmethod
    async def initialize(self) -> None:
        """One-time setup (e.g. seed prices, open HTTP sessions)."""

    @abstractmethod
    async def get_current_prices(self, tickers: list[str]) -> list[PriceUpdate]:
        """
        Fetch the current price for each ticker in *tickers*.

        Returns a (possibly partial) list — implementations may omit tickers
        that are unavailable rather than raising.

        Raises:
            MarketDataError: if the whole request fails (auth, network, etc.)
        """

    async def shutdown(self) -> None:
        """Release resources (e.g. close HTTP sessions). Override as needed."""
