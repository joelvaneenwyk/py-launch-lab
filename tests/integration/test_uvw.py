"""
Integration tests: uvw scenarios.

TODO(M3): Implement.
"""

import sys

import pytest


@pytest.fixture(autouse=True)
def require_windows():
    if sys.platform != "win32":
        pytest.skip("uvw is Windows-only")


def test_placeholder():
    """Placeholder — TODO(M3): implement uvw tests."""
    pass
