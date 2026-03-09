"""
Unit tests for Windows detection module (detect_windows.py).

On non-Windows these tests validate the graceful-degradation path —
all public functions should return safe defaults (None / empty list).
"""

import sys

import pytest

from launch_lab.detect_windows import (
    detect_console_host,
    detect_visible_window,
    get_creation_flags,
    get_process_tree,
    is_windows,
)


class TestIsWindows:
    def test_returns_bool(self):
        assert isinstance(is_windows(), bool)

    def test_matches_platform(self):
        assert is_windows() == (sys.platform == "win32")


class TestNonWindowsDefaults:
    """On non-Windows all detection functions should return safe defaults."""

    @pytest.mark.skipif(sys.platform == "win32", reason="Non-Windows test only")
    def test_get_process_tree_returns_empty(self):
        assert get_process_tree(1) == []

    @pytest.mark.skipif(sys.platform == "win32", reason="Non-Windows test only")
    def test_detect_visible_window_returns_none(self):
        assert detect_visible_window(1) is None

    @pytest.mark.skipif(sys.platform == "win32", reason="Non-Windows test only")
    def test_detect_console_host_returns_none(self):
        assert detect_console_host(1) is None

    @pytest.mark.skipif(sys.platform == "win32", reason="Non-Windows test only")
    def test_get_creation_flags_returns_none(self):
        assert get_creation_flags(1) is None


class TestConsoleHostNames:
    """Validate that the CONSOLE_HOST_NAMES set is correctly defined."""

    def test_conhost_in_set(self):
        from launch_lab.detect_windows import _CONSOLE_HOST_NAMES

        assert "conhost.exe" in _CONSOLE_HOST_NAMES

    def test_windowsterminal_in_set(self):
        from launch_lab.detect_windows import _CONSOLE_HOST_NAMES

        assert "windowsterminal.exe" in _CONSOLE_HOST_NAMES
