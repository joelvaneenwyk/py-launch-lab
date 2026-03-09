"""
Windows PE header inspection.

Reads the IMAGE_NT_HEADERS from a Windows executable and returns the
subsystem value.  On non-Windows or for non-PE files, returns gracefully.

References:
    https://learn.microsoft.com/en-us/windows/win32/debug/pe-format
"""

from __future__ import annotations

import struct
from pathlib import Path
from typing import BinaryIO

from launch_lab.models import Subsystem

# PE constants
_IMAGE_DOS_SIGNATURE = 0x5A4D      # 'MZ'
_IMAGE_NT_SIGNATURE = 0x00004550   # 'PE\0\0'
_SUBSYSTEM_CUI = 3                 # Console
_SUBSYSTEM_GUI = 2                 # Windows GUI


def inspect_pe(path: str | Path) -> Subsystem | None:
    """
    Inspect a PE executable and return its subsystem classification.

    Returns:
        Subsystem.GUI  — IMAGE_SUBSYSTEM_WINDOWS_GUI
        Subsystem.CUI  — IMAGE_SUBSYSTEM_WINDOWS_CUI
        Subsystem.NOT_PE — file exists but is not a PE executable
        Subsystem.UNKNOWN — PE found but subsystem not recognised
        None — file not found or unreadable
    """
    path = Path(path)
    if not path.exists():
        return None

    try:
        with path.open("rb") as f:
            return _read_subsystem(f)
    except (OSError, struct.error):
        return None


def _read_subsystem(f: BinaryIO) -> Subsystem:
    """Read PE subsystem from an open binary file."""
    # DOS header — check MZ signature
    dos_sig = struct.unpack("<H", f.read(2))[0]
    if dos_sig != _IMAGE_DOS_SIGNATURE:
        return Subsystem.NOT_PE

    # Offset to PE header is at 0x3C
    f.seek(0x3C)
    pe_offset = struct.unpack("<I", f.read(4))[0]

    # PE signature
    f.seek(pe_offset)
    pe_sig = struct.unpack("<I", f.read(4))[0]
    if pe_sig != _IMAGE_NT_SIGNATURE:
        return Subsystem.NOT_PE

    # COFF header (20 bytes) — skip
    f.seek(pe_offset + 4 + 20)

    # Optional header — first 2 bytes are Magic (PE32 = 0x10B, PE32+ = 0x20B)
    magic = struct.unpack("<H", f.read(2))[0]
    if magic == 0x10B:
        # PE32 — Subsystem is at offset 68 from start of optional header
        f.seek(pe_offset + 4 + 20 + 68)
    elif magic == 0x20B:
        # PE32+ — Subsystem is at offset 68 from start of optional header (same)
        f.seek(pe_offset + 4 + 20 + 68)
    else:
        return Subsystem.UNKNOWN

    subsystem = struct.unpack("<H", f.read(2))[0]
    if subsystem == _SUBSYSTEM_GUI:
        return Subsystem.GUI
    if subsystem == _SUBSYSTEM_CUI:
        return Subsystem.CUI
    return Subsystem.UNKNOWN
