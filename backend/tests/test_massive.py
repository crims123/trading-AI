"""
Unit tests for app.market.massive — MassiveDataSource.

All HTTP calls are intercepted with respx so no real network traffic occurs.
"""

import json
import time

import httpx
import pytest
import respx

from app.market.interface import InvalidTickerError, MarketDataError, RateLimitError
from app.market.massive import MassiveDataSource, _SNAPSHOT_PATH

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_FAKE_KEY = "test-api-key-abc123"
_MOCK_BASE = "https://api.polygon.io"
_MOCK_URL = f"{_MOCK_BASE}{_SNAPSHOT_PATH}"


def _make_snapshot(
    ticker: str,
    current: float,
    prev_close: float,
    volume: int = 1_000_000,
    high: float = None,
    low: float = None,
    updated_ns: int = None,
) -> dict:
    """Build a fake Polygon.io ticker snapshot dict."""
    if updated_ns is None:
        updated_ns = int(time.time() * 1e9)
    snap = {
        "ticker": ticker,
        "day": {
            "c": current,
            "v": volume,
        },
        "prevDay": {
            "c": prev_close,
        },
        "lastTrade": {"p": current},
        "updated": updated_ns,
    }
    if high is not None:
        snap["day"]["h"] = high
    if low is not None:
        snap["day"]["l"] = low
    return snap


def _api_response(tickers_data: list[dict]) -> dict:
    return {"tickers": tickers_data, "status": "OK"}


# ---------------------------------------------------------------------------
# Initialisation
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_initialize_creates_http_client():
    src = MassiveDataSource(api_key=_FAKE_KEY)
    assert src._client is None
    await src.initialize()
    assert src._client is not None
    await src.shutdown()


@pytest.mark.asyncio
async def test_shutdown_closes_client():
    src = MassiveDataSource(api_key=_FAKE_KEY)
    await src.initialize()
    await src.shutdown()
    assert src._client is None


@pytest.mark.asyncio
async def test_shutdown_without_initialize_is_safe():
    src = MassiveDataSource(api_key=_FAKE_KEY)
    await src.shutdown()  # Should not raise


# ---------------------------------------------------------------------------
# Happy-path price fetching
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
@respx.mock
async def test_get_current_prices_single_ticker():
    src = MassiveDataSource(api_key=_FAKE_KEY, base_url=_MOCK_BASE)
    await src.initialize()

    snap = _make_snapshot("AAPL", current=190.5, prev_close=188.0, volume=28_000_000, high=192.0, low=188.5)
    respx.get(_MOCK_URL).mock(return_value=httpx.Response(200, json=_api_response([snap])))

    updates = await src.get_current_prices(["AAPL"])
    assert len(updates) == 1
    u = updates[0]
    assert u.ticker == "AAPL"
    assert u.price == pytest.approx(190.5)
    assert u.previous_price == pytest.approx(188.0)
    assert u.volume == 28_000_000
    assert u.high == pytest.approx(192.0)
    assert u.low == pytest.approx(188.5)

    await src.shutdown()


@pytest.mark.asyncio
@respx.mock
async def test_get_current_prices_multiple_tickers():
    src = MassiveDataSource(api_key=_FAKE_KEY, base_url=_MOCK_BASE)
    await src.initialize()

    snaps = [
        _make_snapshot("AAPL", 190.5, 188.0),
        _make_snapshot("GOOGL", 175.0, 172.0),
        _make_snapshot("MSFT", 422.0, 420.0),
    ]
    respx.get(_MOCK_URL).mock(return_value=httpx.Response(200, json=_api_response(snaps)))

    updates = await src.get_current_prices(["AAPL", "GOOGL", "MSFT"])
    assert len(updates) == 3
    tickers = {u.ticker for u in updates}
    assert tickers == {"AAPL", "GOOGL", "MSFT"}

    await src.shutdown()


@pytest.mark.asyncio
async def test_get_current_prices_empty_list_returns_empty():
    """Empty ticker list must return immediately without making an HTTP call."""
    src = MassiveDataSource(api_key=_FAKE_KEY)
    await src.initialize()
    updates = await src.get_current_prices([])
    assert updates == []
    await src.shutdown()


@pytest.mark.asyncio
@respx.mock
async def test_timestamp_converted_from_nanoseconds_to_milliseconds():
    src = MassiveDataSource(api_key=_FAKE_KEY, base_url=_MOCK_BASE)
    await src.initialize()

    ns_ts = 1_605_195_918_306_274_000
    snap = _make_snapshot("AAPL", 190.5, 188.0, updated_ns=ns_ts)
    respx.get(_MOCK_URL).mock(return_value=httpx.Response(200, json=_api_response([snap])))

    updates = await src.get_current_prices(["AAPL"])
    expected_ms = ns_ts // 1_000_000
    assert updates[0].timestamp == expected_ms

    await src.shutdown()


@pytest.mark.asyncio
@respx.mock
async def test_previous_price_falls_back_to_cached_value():
    """If prevDay is missing, the last seen price should be used as previous_price."""
    src = MassiveDataSource(api_key=_FAKE_KEY, base_url=_MOCK_BASE)
    await src.initialize()

    # First call — prevDay provided; caches current price
    snap1 = _make_snapshot("AAPL", 190.5, 188.0)
    respx.get(_MOCK_URL).mock(return_value=httpx.Response(200, json=_api_response([snap1])))
    await src.get_current_prices(["AAPL"])

    # Second call — no prevDay; previous_price should be the first call's price
    snap2 = {"ticker": "AAPL", "day": {"c": 192.0, "v": 1000}, "updated": int(time.time() * 1e9)}
    respx.get(_MOCK_URL).mock(return_value=httpx.Response(200, json=_api_response([snap2])))
    updates = await src.get_current_prices(["AAPL"])
    assert updates[0].previous_price == pytest.approx(190.5)

    await src.shutdown()


@pytest.mark.asyncio
@respx.mock
async def test_snapshot_without_ticker_field_is_skipped():
    src = MassiveDataSource(api_key=_FAKE_KEY, base_url=_MOCK_BASE)
    await src.initialize()

    bad_snap = {"day": {"c": 100.0}}  # missing "ticker"
    respx.get(_MOCK_URL).mock(return_value=httpx.Response(200, json=_api_response([bad_snap])))

    updates = await src.get_current_prices(["AAPL"])
    assert updates == []

    await src.shutdown()


@pytest.mark.asyncio
@respx.mock
async def test_snapshot_without_price_is_skipped():
    src = MassiveDataSource(api_key=_FAKE_KEY, base_url=_MOCK_BASE)
    await src.initialize()

    bad_snap = {"ticker": "AAPL", "day": {}, "prevDay": {}}  # no close price
    respx.get(_MOCK_URL).mock(return_value=httpx.Response(200, json=_api_response([bad_snap])))

    updates = await src.get_current_prices(["AAPL"])
    assert updates == []

    await src.shutdown()


# ---------------------------------------------------------------------------
# Error handling
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
@respx.mock
async def test_raises_market_data_error_on_401():
    src = MassiveDataSource(api_key="bad-key", base_url=_MOCK_BASE)
    await src.initialize()

    respx.get(_MOCK_URL).mock(return_value=httpx.Response(401))

    with pytest.raises(MarketDataError, match="401"):
        await src.get_current_prices(["AAPL"])

    await src.shutdown()


@pytest.mark.asyncio
@respx.mock
async def test_raises_market_data_error_on_403():
    src = MassiveDataSource(api_key=_FAKE_KEY, base_url=_MOCK_BASE)
    await src.initialize()

    respx.get(_MOCK_URL).mock(return_value=httpx.Response(403))

    with pytest.raises(MarketDataError, match="403"):
        await src.get_current_prices(["AAPL"])

    await src.shutdown()


@pytest.mark.asyncio
@respx.mock
async def test_raises_rate_limit_error_on_429():
    src = MassiveDataSource(api_key=_FAKE_KEY, base_url=_MOCK_BASE)
    await src.initialize()

    respx.get(_MOCK_URL).mock(return_value=httpx.Response(429))

    with pytest.raises(RateLimitError):
        await src.get_current_prices(["AAPL"])

    await src.shutdown()


@pytest.mark.asyncio
@respx.mock
async def test_raises_invalid_ticker_error_on_404():
    src = MassiveDataSource(api_key=_FAKE_KEY, base_url=_MOCK_BASE)
    await src.initialize()

    respx.get(_MOCK_URL).mock(return_value=httpx.Response(404))

    with pytest.raises(InvalidTickerError):
        await src.get_current_prices(["FAKECORP"])

    await src.shutdown()


@pytest.mark.asyncio
@respx.mock
async def test_raises_market_data_error_on_500():
    src = MassiveDataSource(api_key=_FAKE_KEY, base_url=_MOCK_BASE)
    await src.initialize()

    respx.get(_MOCK_URL).mock(return_value=httpx.Response(500))

    with pytest.raises(MarketDataError, match="500"):
        await src.get_current_prices(["AAPL"])

    await src.shutdown()


@pytest.mark.asyncio
@respx.mock
async def test_raises_market_data_error_on_timeout():
    src = MassiveDataSource(api_key=_FAKE_KEY, base_url=_MOCK_BASE)
    await src.initialize()

    respx.get(_MOCK_URL).mock(side_effect=httpx.TimeoutException("timeout"))

    with pytest.raises(MarketDataError, match="timed out"):
        await src.get_current_prices(["AAPL"])

    await src.shutdown()


@pytest.mark.asyncio
@respx.mock
async def test_raises_market_data_error_on_network_failure():
    src = MassiveDataSource(api_key=_FAKE_KEY, base_url=_MOCK_BASE)
    await src.initialize()

    respx.get(_MOCK_URL).mock(side_effect=httpx.ConnectError("connection refused"))

    with pytest.raises(MarketDataError, match="Network error"):
        await src.get_current_prices(["AAPL"])

    await src.shutdown()


@pytest.mark.asyncio
async def test_raises_market_data_error_if_not_initialised():
    """Calling get_current_prices before initialize() must raise MarketDataError."""
    src = MassiveDataSource(api_key=_FAKE_KEY)
    with pytest.raises(MarketDataError, match="not initialised"):
        await src.get_current_prices(["AAPL"])


# ---------------------------------------------------------------------------
# Factory integration
# ---------------------------------------------------------------------------


def test_factory_returns_simulator_when_no_key(monkeypatch):
    monkeypatch.delenv("MASSIVE_API_KEY", raising=False)
    from app.market.factory import create_market_data_source
    from app.market.simulator import SimulatorDataSource
    source = create_market_data_source()
    assert isinstance(source, SimulatorDataSource)


def test_factory_returns_massive_when_key_set(monkeypatch):
    monkeypatch.setenv("MASSIVE_API_KEY", "fake-key-xyz")
    from app.market.factory import create_market_data_source
    source = create_market_data_source()
    assert isinstance(source, MassiveDataSource)
