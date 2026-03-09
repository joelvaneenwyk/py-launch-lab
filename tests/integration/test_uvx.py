"""
Integration tests: uvx scenarios.

TODO(M3): Implement.
"""

import shutil

import pytest


@pytest.fixture(autouse=True)
def require_uv():
    if shutil.which("uv") is None:
        pytest.skip("uv not on PATH")


def test_placeholder():
    """Placeholder — TODO(M3): implement uvx tests."""
    pass
