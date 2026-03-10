"""
Integration tests: pyshim-win Rust shim scenarios.

TODO(M4): Implement.
"""

import sys

import pytest


@pytest.fixture(autouse=True)
def require_windows():
    if sys.platform != "win32":
        pytest.skip("pyshim-win is Windows-only")


def test_placeholder():
    """Placeholder — TODO(M4): implement pyshim-win integration tests."""
    pass
