"""
Massive (Polygon.io) market data source.

Uses the Polygon.io REST v2 snapshot endpoint via httpx — no third-party
Polygon SDK required, keeping the dependency footprint minimal.

Endpoint reference:
  GET /v2/snapshot/locale/us/markets/stocks/tickers
  Query params: tickers=AAPL,GOOGL,... apiKey=<key>

Response shape:
  {
    "tickers": [
      {
        "ticker": "AAPL",
        "day":     {"c": 190.5, "h": 192.0, "l": 188.0, "v": 28000000},
        "prevDay": {"c": 188.0},
        "lastTrade": {"p": 190.6},
        "updated": 1605195918306274000   // nanoseconds
      }, ...
    ]
  }
"""

import time
from typing import Optional

import httpx

from .interface import (
    InvalidTickerError,
    MarketDataError,
    MarketDataSource,
    PriceUpdate,
    RateLimitError,
)

_SNAPSHOT_PATH = "/v2/snapshot/locale/us/markets/stocks/tickers"
_BASE_URL = "https://api.polygon.io"
_NS_PER_MS = 1_000_000


class MassiveDataSource(MarketDataSource):
    """
    Fetches real market prices from the Massive / Polygon.io REST API.

    A single bulk snapshot call covers all tickers, keeping quota usage low.
    Previous prices are cached locally so the first tick always has a valid
    `previous_price` even when `prevDay` is absent in the response.
    """

    def __init__(self, api_key: str, base_url: str = _BASE_URL) -> None:
        self._api_key = api_key
        self._base_url = base_url
        self._client: Optional[httpx.AsyncClient] = None
        # Fallback: remember last seen price so we always have a previous_price
        self._last_prices: dict[str, float] = {}

    async def initialize(self) -> None:
        """Open the shared async HTTP client."""
        self._client = httpx.AsyncClient(
            base_url=self._base_url,
            timeout=10.0,
            headers={"User-Agent": "FinAlly/1.0"},
        )

    async def shutdown(self) -> None:
        """Close the HTTP client and release connections."""
        if self._client is not None:
            await self._client.aclose()
            self._client = None

    async def get_current_prices(self, tickers: list[str]) -> list[PriceUpdate]:
        """Fetch prices for all *tickers* in a single API call."""
        if not tickers:
            return []

        if self._client is None:
            raise MarketDataError("MassiveDataSource not initialised — call initialize() first.")

        params = {
            "tickers": ",".join(tickers),
            "apiKey": self._api_key,
        }

        try:
            response = await self._client.get(_SNAPSHOT_PATH, params=params)
        except httpx.TimeoutException as exc:
            raise MarketDataError(f"Massive API request timed out: {exc}") from exc
        except httpx.RequestError as exc:
            raise MarketDataError(f"Network error contacting Massive API: {exc}") from exc

        self._raise_for_status(response)

        payload = response.json()
        ticker_list = payload.get("tickers") or []

        updates: list[PriceUpdate] = []
        timestamp_ms = int(time.time() * 1000)

        for snap in ticker_list:
            update = self._parse_snapshot(snap, timestamp_ms)
            if update is not None:
                updates.append(update)

        return updates

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _raise_for_status(self, response: httpx.Response) -> None:
        code = response.status_code
        if code == 200:
            return
        if code == 401:
            raise MarketDataError("Invalid Massive API key (HTTP 401).")
        if code == 403:
            raise MarketDataError("Massive API access forbidden (HTTP 403).")
        if code == 404:
            raise InvalidTickerError("Ticker not found on Massive API (HTTP 404).")
        if code == 429:
            raise RateLimitError("Massive API rate limit exceeded (HTTP 429).")
        raise MarketDataError(f"Massive API returned unexpected status {code}.")

    def _parse_snapshot(
        self, snap: dict, fallback_timestamp_ms: int
    ) -> Optional[PriceUpdate]:
        ticker: Optional[str] = snap.get("ticker")
        if not ticker:
            return None

        day: dict = snap.get("day") or {}
        prev_day: dict = snap.get("prevDay") or {}
        last_trade: dict = snap.get("lastTrade") or {}

        # Best-effort current price: day close → last trade price
        current_price: Optional[float] = day.get("c") or last_trade.get("p")
        if current_price is None:
            return None
        current_price = float(current_price)

        # Previous price: yesterday's close → locally cached last price → current
        previous_price: Optional[float] = prev_day.get("c")
        if previous_price is None:
            previous_price = self._last_prices.get(ticker)
        if previous_price is None:
            previous_price = current_price
        previous_price = float(previous_price)

        # Remember this price for the next tick's previous_price fallback
        self._last_prices[ticker] = current_price

        # Polygon timestamps are nanoseconds; convert to milliseconds
        raw_ts = snap.get("updated")
        if raw_ts:
            timestamp_ms = int(raw_ts) // _NS_PER_MS
        else:
            timestamp_ms = fallback_timestamp_ms

        return PriceUpdate(
            ticker=ticker,
            price=current_price,
            previous_price=previous_price,
            timestamp=timestamp_ms,
            volume=int(day.get("v") or 0),
            high=float(day["h"]) if day.get("h") is not None else None,
            low=float(day["l"]) if day.get("l") is not None else None,
        )
