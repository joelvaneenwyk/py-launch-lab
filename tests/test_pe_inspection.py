"""
Tests for PE header inspection (inspect_pe.py).

On non-Windows platforms these tests validate only the graceful-degradation
path.  On Windows they can be extended to inspect real executables.
"""

import sys
from pathlib import Path

import pytest

from launch_lab.inspect_pe import inspect_pe
from launch_lab.models import Subsystem


def test_inspect_nonexistent_file_returns_none():
    assert inspect_pe("/this/path/does/not/exist.exe") is None


def test_inspect_non_pe_file_returns_not_pe(tmp_path):
    f = tmp_path / "notape.exe"
    f.write_bytes(b"This is not a PE file")
    result = inspect_pe(f)
    assert result == Subsystem.NOT_PE


def test_inspect_truncated_file_returns_none_or_not_pe(tmp_path):
    """A file that starts with MZ but is too short to contain a full header."""
    f = tmp_path / "truncated.exe"
    f.write_bytes(b"MZ" + b"\x00" * 10)  # MZ but far too short
    result = inspect_pe(f)
    # Either NOT_PE or None — both are acceptable for a truncated file
    assert result in (Subsystem.NOT_PE, None)


@pytest.mark.skipif(sys.platform != "win32", reason="Windows-only test")
def test_inspect_python_exe_on_windows():
    """On Windows, python.exe should be a CUI executable."""
    import shutil

    python_path = shutil.which("python")
    if python_path is None:
        pytest.skip("python not on PATH")
    result = inspect_pe(python_path)
    assert result == Subsystem.CUI


@pytest.mark.skipif(sys.platform != "win32", reason="Windows-only test")
def test_inspect_pythonw_exe_on_windows():
    """On Windows, pythonw.exe should be a GUI executable."""
    import shutil

    pythonw_path = shutil.which("pythonw")
    if pythonw_path is None:
        pytest.skip("pythonw not on PATH")
    result = inspect_pe(pythonw_path)
    assert result == Subsystem.GUI
