"""
GBM-based market price simulator.

Prices evolve each tick via:
    S(t+1) = S(t) * exp((μ - σ²/2)*dt + σ*√dt*Z)
where Z ~ N(0,1).

A shared market_factor creates mild correlation across tickers.
Occasional random "events" (1 % per tick) produce dramatic ±3 % jumps.
"""

import time
from typing import Dict, Optional

import numpy as np

from .interface import MarketDataError, MarketDataSource, PriceUpdate

# ---------------------------------------------------------------------------
# Default seed data (realistic 2024-era prices and per-ticker volatilities)
# ---------------------------------------------------------------------------

DEFAULT_SEED_PRICES: Dict[str, float] = {
    "AAPL": 190.50,
    "GOOGL": 175.25,
    "MSFT": 422.75,
    "AMZN": 182.50,
    "TSLA": 245.30,
    "NVDA": 875.20,
    "META": 508.40,
    "JPM": 195.80,
    "V": 288.60,
    "NFLX": 425.75,
}

DEFAULT_VOLATILITIES: Dict[str, float] = {
    "AAPL": 0.015,
    "GOOGL": 0.016,
    "MSFT": 0.014,
    "AMZN": 0.018,
    "TSLA": 0.028,
    "NVDA": 0.025,
    "META": 0.020,
    "JPM": 0.012,
    "V": 0.011,
    "NFLX": 0.022,
}

DEFAULT_DRIFT: float = 0.0001  # ~25 % annualised at ~1000 ticks/day


class MarketSimulator:
    """
    Core GBM engine — ticker-agnostic, synchronous, easily unit-tested.

    All randomness is isolated in *rng* so tests can use a fixed seed.
    """

    def __init__(self, seed: Optional[int] = 42) -> None:
        self.rng = np.random.RandomState(seed)
        self.prices: Dict[str, float] = {}
        self.previous_prices: Dict[str, float] = {}
        self.params: Dict[str, Dict[str, float]] = {}
        self.tick_count: int = 0
        # Shared factor that nudges all tickers in the same direction
        self.market_factor: float = 1.0

    def add_ticker(
        self,
        ticker: str,
        initial_price: float,
        drift: float = DEFAULT_DRIFT,
        volatility: float = 0.02,
    ) -> None:
        """Register a ticker with its starting price and GBM parameters."""
        self.prices[ticker] = initial_price
        self.previous_prices[ticker] = initial_price
        self.params[ticker] = {"drift": drift, "volatility": volatility}

    def step(self, dt: float = 1.0) -> None:
        """Advance every tracked ticker by one time step."""
        self.tick_count += 1

        # 5 % chance of a small market-wide shock (drives inter-ticker correlation)
        if self.rng.random() < 0.05:
            self.market_factor *= float(1 + self.rng.normal(0, 0.02))
            self.market_factor = float(np.clip(self.market_factor, 0.95, 1.05))

        for ticker, prev_price in self.prices.items():
            params = self.params[ticker]
            mu = params["drift"] * dt
            sigma = params["volatility"] * np.sqrt(dt)
            dW = float(self.rng.normal(0, 1))

            # 1 % per-ticker chance of a sudden news-style event
            event_factor = 1.0
            if self.rng.random() < 0.01:
                event_factor = float(1 + self.rng.normal(0, 0.03))

            log_return = mu - (sigma ** 2) / 2 + sigma * dW
            # Blend individual GBM with the shared market factor
            new_price = (
                prev_price
                * float(np.exp(log_return))
                * (1 + (self.market_factor - 1) * 0.5)
                * event_factor
            )

            # Hard clamp: never let a price halve or double in a single tick
            new_price = float(np.clip(new_price, prev_price * 0.5, prev_price * 2.0))

            self.previous_prices[ticker] = prev_price
            self.prices[ticker] = new_price

    def get_price(self, ticker: str) -> Optional[float]:
        return self.prices.get(ticker)

    def get_previous_price(self, ticker: str) -> Optional[float]:
        return self.previous_prices.get(ticker)

    def get_all_prices(self) -> Dict[str, float]:
        return dict(self.prices)


class SimulatorDataSource(MarketDataSource):
    """
    MarketDataSource adapter that wraps MarketSimulator.

    Calls step() at most once per 500 ms of wall-clock time so that concurrent
    callers all see the same "current" tick rather than racing ahead.
    """

    def __init__(self, seed: Optional[int] = 42) -> None:
        self.simulator = MarketSimulator(seed=seed)
        self._last_step_time: float = 0.0
        self._step_interval: float = 0.5  # seconds between GBM steps

    async def initialize(self) -> None:
        """Seed simulator with the default 10 tickers and take an initial step."""
        for ticker, price in DEFAULT_SEED_PRICES.items():
            volatility = DEFAULT_VOLATILITIES.get(ticker, 0.02)
            self.simulator.add_ticker(ticker, initial_price=price, volatility=volatility)
        # Prime the cache so first callers don't see stale zeros
        self.simulator.step()
        self._last_step_time = time.monotonic()

    async def get_current_prices(self, tickers: list[str]) -> list[PriceUpdate]:
        """Return simulated prices, advancing the simulation if enough time has passed."""
        now = time.monotonic()
        if now - self._last_step_time >= self._step_interval:
            self.simulator.step()
            self._last_step_time = now

        timestamp_ms = int(time.time() * 1000)
        updates: list[PriceUpdate] = []

        for ticker in tickers:
            price = self.simulator.get_price(ticker)
            prev = self.simulator.get_previous_price(ticker)
            if price is None or prev is None:
                continue
            volume = int(abs(float(self.simulator.rng.normal(1_000_000, 200_000))))
            updates.append(
                PriceUpdate(
                    ticker=ticker,
                    price=price,
                    previous_price=prev,
                    timestamp=timestamp_ms,
                    volume=volume,
                )
            )

        return updates

    def add_ticker(self, ticker: str, initial_price: Optional[float] = None) -> None:
        """Dynamically register a new ticker (called when user adds to watchlist)."""
        if ticker in self.simulator.prices:
            return
        price = initial_price or DEFAULT_SEED_PRICES.get(ticker, 100.0)
        volatility = DEFAULT_VOLATILITIES.get(ticker, 0.02)
        self.simulator.add_ticker(ticker, initial_price=price, volatility=volatility)
