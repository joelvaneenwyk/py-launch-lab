"""
Windows-specific process and window detection.

This module is only meaningful on win32.  All public functions return safe
defaults (None / empty list) on other platforms so the rest of the codebase
can import it unconditionally.

TODO(M2): Implement actual Windows detection using ctypes / psutil.
"""

from __future__ import annotations

import sys
from typing import Optional

from launch_lab.models import ProcessInfo

_IS_WINDOWS = sys.platform == "win32"


def is_windows() -> bool:
    """Return True if running on Windows."""
    return _IS_WINDOWS


def get_process_tree(pid: int) -> list[ProcessInfo]:
    """
    Return a snapshot of the process tree rooted at `pid`.

    TODO(M2): Use psutil or Windows API to walk the process tree.
    """
    if not _IS_WINDOWS:
        return []
    # TODO(M2): Implement using psutil.Process(pid).children(recursive=True)
    return []


def detect_visible_window(pid: int) -> Optional[bool]:
    """
    Return True if a visible top-level window is associated with `pid`.

    TODO(M2): Use EnumWindows + GetWindowThreadProcessId via ctypes.
    """
    if not _IS_WINDOWS:
        return None
    # TODO(M2): Implement using ctypes.windll.user32.EnumWindows
    return None


def detect_console_host(pid: int) -> Optional[bool]:
    """
    Return True if a console host (conhost.exe / Windows Terminal) is
    present in the process tree for `pid`.

    TODO(M2): Walk process tree and check for known console host names.
    """
    if not _IS_WINDOWS:
        return None
    # TODO(M2): Check for 'conhost.exe' or 'WindowsTerminal.exe' in tree
    return None


def get_creation_flags(pid: int) -> Optional[int]:
    """
    Return the PROCESS_CREATION_FLAGS used when `pid` was created.

    TODO(M2): Use NtQueryInformationProcess or a similar mechanism.
    """
    if not _IS_WINDOWS:
        return None
    # TODO(M2): Implement via ctypes or a helper DLL
    return None
