"""
Shared pytest fixtures for the backend test suite.
"""

import pytest


@pytest.fixture(autouse=True)
def reset_env(monkeypatch):
    """Ensure MASSIVE_API_KEY is unset by default so tests use the simulator."""
    monkeypatch.delenv("MASSIVE_API_KEY", raising=False)
