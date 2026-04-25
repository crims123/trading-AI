"""
Factory function that selects the market data source based on environment.

If MASSIVE_API_KEY is set and non-empty → MassiveDataSource (real prices).
Otherwise                               → SimulatorDataSource (GBM simulation).
"""

import os

from .interface import MarketDataSource
from .massive import MassiveDataSource
from .simulator import SimulatorDataSource


def create_market_data_source() -> MarketDataSource:
    """
    Return the appropriate MarketDataSource for the current environment.

    Reading the key inside the factory (not at import time) means tests can
    patch os.environ without needing to reload the module.
    """
    api_key = os.getenv("MASSIVE_API_KEY", "").strip()

    if api_key:
        print("[market] MASSIVE_API_KEY detected — using Massive API for real market data.")
        return MassiveDataSource(api_key=api_key)

    print("[market] No MASSIVE_API_KEY — using built-in GBM market simulator.")
    return SimulatorDataSource()
