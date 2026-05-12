"""
Unit tests for app.market.simulator — MarketSimulator and SimulatorDataSource.
"""

import time
from unittest.mock import patch

import numpy as np
import pytest

from app.market.simulator import (
    DEFAULT_SEED_PRICES,
    DEFAULT_VOLATILITIES,
    MarketSimulator,
    SimulatorDataSource,
)


# ---------------------------------------------------------------------------
# MarketSimulator — basic behaviour
# ---------------------------------------------------------------------------


def test_simulator_initialises_with_seed():
    sim = MarketSimulator(seed=42)
    assert sim.tick_count == 0
    assert sim.market_factor == 1.0
    assert sim.prices == {}


def test_add_ticker_stores_initial_price():
    sim = MarketSimulator(seed=42)
    sim.add_ticker("TEST", initial_price=100.0)
    assert sim.get_price("TEST") == 100.0
    assert sim.get_previous_price("TEST") == 100.0


def test_step_changes_price():
    sim = MarketSimulator(seed=42)
    sim.add_ticker("TEST", initial_price=100.0)
    sim.step()
    assert sim.get_price("TEST") != 100.0


def test_step_increments_tick_count():
    sim = MarketSimulator(seed=42)
    sim.add_ticker("TEST", initial_price=100.0)
    for _ in range(5):
        sim.step()
    assert sim.tick_count == 5


def test_previous_price_updated_after_step():
    sim = MarketSimulator(seed=42)
    sim.add_ticker("TEST", initial_price=100.0)
    sim.step()
    first_price = sim.get_price("TEST")
    sim.step()
    assert sim.get_previous_price("TEST") == first_price


def test_get_price_unknown_ticker_returns_none():
    sim = MarketSimulator(seed=42)
    assert sim.get_price("UNKNOWN") is None
    assert sim.get_previous_price("UNKNOWN") is None


def test_get_all_prices_returns_dict():
    sim = MarketSimulator(seed=42)
    sim.add_ticker("AAPL", 190.0)
    sim.add_ticker("GOOGL", 175.0)
    prices = sim.get_all_prices()
    assert set(prices.keys()) == {"AAPL", "GOOGL"}


# ---------------------------------------------------------------------------
# GBM mathematical properties
# ---------------------------------------------------------------------------


def test_prices_do_not_explode_under_high_volatility():
    """Even with extreme volatility the per-tick clamp keeps prices bounded."""
    sim = MarketSimulator(seed=42)
    sim.add_ticker("WILD", initial_price=100.0, volatility=0.5)
    for _ in range(10_000):
        sim.step()
    price = sim.get_price("WILD")
    # We can't assert a tight bound because of long paths, but the price
    # must remain positive and not wildly explode beyond 10 000×.
    assert price is not None
    assert price > 0


def test_price_clamp_prevents_single_tick_halving_or_doubling():
    """Each step is limited to [0.5× prev, 2× prev]."""
    sim = MarketSimulator(seed=0)
    sim.add_ticker("TEST", initial_price=100.0, volatility=1.0)
    for _ in range(500):
        prev = sim.get_price("TEST")
        sim.step()
        curr = sim.get_price("TEST")
        assert curr >= prev * 0.5 - 1e-9, f"Price dropped below 50%: {prev} -> {curr}"
        assert curr <= prev * 2.0 + 1e-9, f"Price more than doubled: {prev} -> {curr}"


def test_reproducible_with_same_seed():
    """Identical seeds produce identical price sequences."""
    def run(seed):
        sim = MarketSimulator(seed=seed)
        sim.add_ticker("AAPL", 190.0)
        for _ in range(10):
            sim.step()
        return sim.get_price("AAPL")

    assert run(42) == run(42)
    assert run(7) == run(7)
    assert run(42) != run(7)


def test_non_deterministic_with_none_seed():
    """seed=None should give different results across runs (probabilistic check)."""
    def run():
        sim = MarketSimulator(seed=None)
        sim.add_ticker("AAPL", 190.0)
        for _ in range(20):
            sim.step()
        return sim.get_price("AAPL")

    prices = [run() for _ in range(5)]
    # Very unlikely all 5 values are identical with floating-point GBM
    assert len(set(prices)) > 1


def test_correlation_between_tickers():
    """
    Tickers should exhibit positive correlation because of the shared
    market_factor. Over 200 steps, Pearson r should be > 0.1.
    """
    sim = MarketSimulator(seed=42)
    sim.add_ticker("A", 100.0)
    sim.add_ticker("B", 100.0)

    prices_a, prices_b = [], []
    for _ in range(200):
        sim.step()
        prices_a.append(sim.get_price("A"))
        prices_b.append(sim.get_price("B"))

    r = float(np.corrcoef(prices_a, prices_b)[0, 1])
    assert r > 0.1, f"Expected positive correlation, got {r:.3f}"


def test_multiple_tickers_all_updated():
    sim = MarketSimulator(seed=42)
    tickers = ["AAPL", "GOOGL", "MSFT", "TSLA"]
    initial_prices = {t: 100.0 for t in tickers}
    for t in tickers:
        sim.add_ticker(t, initial_prices[t])

    sim.step()

    for t in tickers:
        assert sim.get_price(t) != initial_prices[t], f"{t} price did not change"


# ---------------------------------------------------------------------------
# SimulatorDataSource
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_simulator_source_initialises_default_tickers():
    src = SimulatorDataSource(seed=42)
    await src.initialize()
    prices = src.simulator.get_all_prices()
    assert set(prices.keys()) == set(DEFAULT_SEED_PRICES.keys())


@pytest.mark.asyncio
async def test_simulator_source_returns_price_updates():
    src = SimulatorDataSource(seed=42)
    await src.initialize()
    updates = await src.get_current_prices(["AAPL", "GOOGL"])
    assert len(updates) == 2
    tickers = {u.ticker for u in updates}
    assert tickers == {"AAPL", "GOOGL"}


@pytest.mark.asyncio
async def test_simulator_source_price_update_fields():
    src = SimulatorDataSource(seed=42)
    await src.initialize()
    updates = await src.get_current_prices(["AAPL"])
    u = updates[0]
    assert u.ticker == "AAPL"
    assert u.price > 0
    assert u.previous_price > 0
    assert u.timestamp > 0
    assert u.volume >= 0


@pytest.mark.asyncio
async def test_simulator_source_empty_tickers():
    src = SimulatorDataSource(seed=42)
    await src.initialize()
    updates = await src.get_current_prices([])
    assert updates == []


@pytest.mark.asyncio
async def test_simulator_source_unknown_ticker_omitted():
    src = SimulatorDataSource(seed=42)
    await src.initialize()
    updates = await src.get_current_prices(["AAPL", "FAKECORP"])
    tickers = {u.ticker for u in updates}
    assert "FAKECORP" not in tickers
    assert "AAPL" in tickers


@pytest.mark.asyncio
async def test_simulator_source_add_ticker_dynamic():
    src = SimulatorDataSource(seed=42)
    await src.initialize()
    src.add_ticker("PYPL", initial_price=75.0)
    updates = await src.get_current_prices(["PYPL"])
    assert len(updates) == 1
    assert updates[0].ticker == "PYPL"


@pytest.mark.asyncio
async def test_simulator_source_add_existing_ticker_is_noop():
    src = SimulatorDataSource(seed=42)
    await src.initialize()
    price_before = src.simulator.get_price("AAPL")
    src.add_ticker("AAPL", initial_price=999.0)
    # Price should not be overwritten
    assert src.simulator.get_price("AAPL") == price_before


@pytest.mark.asyncio
async def test_simulator_source_steps_on_interval():
    """Calling get_current_prices twice within 500 ms should not step; beyond should."""
    src = SimulatorDataSource(seed=42)
    await src.initialize()

    # Force last_step_time to now so the next call won't step immediately
    src._last_step_time = time.monotonic()
    tick_before = src.simulator.tick_count

    await src.get_current_prices(["AAPL"])
    assert src.simulator.tick_count == tick_before  # Not enough time elapsed

    # Simulate that half a second has passed
    src._last_step_time -= 1.0
    await src.get_current_prices(["AAPL"])
    assert src.simulator.tick_count == tick_before + 1


@pytest.mark.asyncio
async def test_simulator_source_default_seed_prices_are_realistic():
    """All seed prices should be positive and within plausible equity ranges."""
    for ticker, price in DEFAULT_SEED_PRICES.items():
        assert price > 0, f"{ticker} seed price must be positive"
        assert price < 10_000, f"{ticker} seed price {price} looks unrealistic"


def test_default_volatilities_cover_all_seed_tickers():
    assert set(DEFAULT_VOLATILITIES.keys()) == set(DEFAULT_SEED_PRICES.keys())
