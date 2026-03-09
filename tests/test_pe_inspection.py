"""
Tests for PE header inspection (inspect_pe.py).

On non-Windows platforms these tests validate only the graceful-degradation
path.  On Windows they can be extended to inspect real executables.
"""

import struct
import sys

import pytest

from launch_lab.inspect_pe import inspect_pe
from launch_lab.models import Subsystem


def _build_synthetic_pe(subsystem: int, *, pe32_plus: bool = False) -> bytes:
    """Build a minimal synthetic PE file with the given subsystem value.

    This creates a byte sequence with a valid DOS header, PE signature,
    COFF header, and Optional header containing the requested subsystem
    field.  It is sufficient for ``inspect_pe`` to classify the file.
    """
    # DOS header: MZ signature + padding up to 0x3C, then PE offset
    dos_header = bytearray(64)
    struct.pack_into("<H", dos_header, 0, 0x5A4D)  # MZ signature
    pe_offset = 64  # PE signature starts right after DOS header
    struct.pack_into("<I", dos_header, 0x3C, pe_offset)

    # PE signature
    pe_sig = struct.pack("<I", 0x00004550)

    # COFF header (20 bytes) — only size matters, contents can be zeros
    coff_header = b"\x00" * 20

    # Optional header — needs Magic and Subsystem at offset 68
    magic = 0x20B if pe32_plus else 0x10B
    opt_header = bytearray(70)  # 68 bytes padding + 2 bytes subsystem
    struct.pack_into("<H", opt_header, 0, magic)
    struct.pack_into("<H", opt_header, 68, subsystem)

    return bytes(dos_header) + pe_sig + coff_header + bytes(opt_header)


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


def test_inspect_synthetic_cui_pe(tmp_path):
    """A synthetic PE32 file with IMAGE_SUBSYSTEM_WINDOWS_CUI (3)."""
    f = tmp_path / "console.exe"
    f.write_bytes(_build_synthetic_pe(subsystem=3))
    assert inspect_pe(f) == Subsystem.CUI


def test_inspect_synthetic_gui_pe(tmp_path):
    """A synthetic PE32 file with IMAGE_SUBSYSTEM_WINDOWS_GUI (2)."""
    f = tmp_path / "gui.exe"
    f.write_bytes(_build_synthetic_pe(subsystem=2))
    assert inspect_pe(f) == Subsystem.GUI


def test_inspect_synthetic_pe32_plus_cui(tmp_path):
    """A synthetic PE32+ (64-bit) file with CUI subsystem."""
    f = tmp_path / "console64.exe"
    f.write_bytes(_build_synthetic_pe(subsystem=3, pe32_plus=True))
    assert inspect_pe(f) == Subsystem.CUI


def test_inspect_synthetic_pe32_plus_gui(tmp_path):
    """A synthetic PE32+ (64-bit) file with GUI subsystem."""
    f = tmp_path / "gui64.exe"
    f.write_bytes(_build_synthetic_pe(subsystem=2, pe32_plus=True))
    assert inspect_pe(f) == Subsystem.GUI


def test_inspect_synthetic_unknown_subsystem(tmp_path):
    """A valid PE with an unrecognised subsystem value returns UNKNOWN."""
    f = tmp_path / "unknown.exe"
    f.write_bytes(_build_synthetic_pe(subsystem=99))
    assert inspect_pe(f) == Subsystem.UNKNOWN


def test_inspect_empty_file_returns_none_or_not_pe(tmp_path):
    """An empty file should return None (unreadable) or NOT_PE."""
    f = tmp_path / "empty.exe"
    f.write_bytes(b"")
    result = inspect_pe(f)
    assert result in (Subsystem.NOT_PE, None)


def test_inspect_bad_pe_signature(tmp_path):
    """DOS header says MZ but the PE signature location has garbage."""
    data = bytearray(128)
    struct.pack_into("<H", data, 0, 0x5A4D)  # MZ
    struct.pack_into("<I", data, 0x3C, 64)  # PE offset at 64
    struct.pack_into("<I", data, 64, 0xDEADBEEF)  # bad PE signature
    f = tmp_path / "badpe.exe"
    f.write_bytes(bytes(data))
    assert inspect_pe(f) == Subsystem.NOT_PE


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


@pytest.mark.skipif(sys.platform != "win32", reason="Windows-only test")
def test_inspect_uv_exe_on_windows():
    """On Windows, uv.exe should be a CUI (console) executable."""
    import shutil

    uv_path = shutil.which("uv")
    if uv_path is None:
        pytest.skip("uv not on PATH")
    result = inspect_pe(uv_path)
    assert result == Subsystem.CUI


@pytest.mark.skipif(sys.platform != "win32", reason="Windows-only test")
def test_inspect_uvw_exe_on_windows():
    """On Windows, uvw.exe (if present) should be a GUI executable."""
    import shutil

    uvw_path = shutil.which("uvw")
    if uvw_path is None:
        pytest.skip("uvw not on PATH")
    result = inspect_pe(uvw_path)
    assert result == Subsystem.GUI
