"""
Unit tests for Windows detection module (detect_windows.py).

On non-Windows these tests validate the graceful-degradation path —
all public functions should return safe defaults (None / empty list).
"""

import sys
from unittest.mock import patch

import pytest

from launch_lab.detect_windows import (
    detect_console_host,
    detect_visible_window,
    get_creation_flags,
    get_process_tree,
    is_windows,
)
from launch_lab.models import ProcessInfo


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


class TestDetectVisibleWindowSubtree:
    """Test that detect_visible_window checks the target PID and its children."""

    def _make_child(self, pid: int, name: str = "child.exe") -> ProcessInfo:
        return ProcessInfo(pid=pid, name=name, exe=None, cmdline=None)

    def test_includes_target_pid_in_enum_call(self):
        """detect_visible_window passes the target PID to _enum_windows_for_pids."""
        captured_pids: list[set[int]] = []

        def fake_enum(pids: set[int]) -> bool:
            captured_pids.append(pids)
            return False

        import launch_lab.detect_windows as dw

        with (
            patch.object(dw, "_IS_WINDOWS", True),
            patch.object(dw, "get_process_tree", return_value=[]),
            patch.object(dw, "_enum_windows_for_pids", side_effect=fake_enum),
        ):
            result = detect_visible_window(42)

        assert result is False
        assert captured_pids == [{42}]

    def test_includes_child_pids_in_enum_call(self):
        """Child PIDs (e.g. conhost.exe) are included in the set passed to _enum_windows_for_pids."""
        child1 = self._make_child(100, "conhost.exe")
        child2 = self._make_child(101, "python.exe")
        captured_pids: list[set[int]] = []

        def fake_enum(pids: set[int]) -> bool:
            captured_pids.append(pids)
            return True

        import launch_lab.detect_windows as dw

        with (
            patch.object(dw, "_IS_WINDOWS", True),
            patch.object(dw, "get_process_tree", return_value=[child1, child2]),
            patch.object(dw, "_enum_windows_for_pids", side_effect=fake_enum),
        ):
            result = detect_visible_window(99)

        assert result is True
        assert captured_pids == [{99, 100, 101}]

    def test_returns_none_on_non_windows(self):
        """On non-Windows, detect_visible_window always returns None."""
        import launch_lab.detect_windows as dw

        with patch.object(dw, "_IS_WINDOWS", False):
            assert detect_visible_window(1) is None
