"""
Windows-specific process and window detection.

This module is only meaningful on win32.  All public functions return safe
defaults (None / empty list) on other platforms so the rest of the codebase
can import it unconditionally.

On Windows the implementation uses:
- ``subprocess`` with ``wmic`` / ``tasklist`` to walk the process tree.
- ``ctypes`` with ``user32.EnumWindows`` to detect visible top-level windows.
- Process tree inspection to detect ``conhost.exe`` presence.
"""

from __future__ import annotations

import logging
import subprocess
import sys

from launch_lab.models import ProcessInfo, Subsystem

_IS_WINDOWS = sys.platform == "win32"
_log = logging.getLogger(__name__)

# Console-host process names (case-insensitive comparison)
_CONSOLE_HOST_NAMES = frozenset({"conhost.exe", "windowsterminal.exe", "openconsole.exe"})


def is_windows() -> bool:
    """Return True if running on Windows."""
    return _IS_WINDOWS


# ---------------------------------------------------------------------------
# Process tree
# ---------------------------------------------------------------------------


def get_process_tree(pid: int) -> list[ProcessInfo]:
    """Return a snapshot of the process tree rooted at *pid*.

    On Windows this queries ``wmic`` / ``tasklist`` for child processes.
    On other platforms an empty list is returned.
    """
    if not _IS_WINDOWS:
        return []

    try:
        return _get_process_tree_wmic(pid)
    except Exception:  # noqa: BLE001
        _log.debug("wmic process tree query failed for pid %d", pid, exc_info=True)
        return []


def _get_process_tree_wmic(pid: int) -> list[ProcessInfo]:
    """Use ``wmic`` to enumerate child processes of *pid*."""
    result = subprocess.run(
        [
            "wmic",
            "process",
            "where",
            f"(ParentProcessId={pid})",
            "get",
            "ProcessId,Name,ExecutablePath,CommandLine",
            "/format:csv",
        ],
        capture_output=True,
        text=True,
        timeout=10,
    )
    infos: list[ProcessInfo] = []
    for line in result.stdout.splitlines():
        parts = line.strip().split(",")
        # CSV columns: Node, CommandLine, ExecutablePath, Name, ProcessId
        if len(parts) < 5:
            continue
        try:
            child_pid = int(parts[-1])
        except (ValueError, IndexError):
            continue
        name = parts[-2] if len(parts) >= 2 else ""
        exe = parts[-3] if len(parts) >= 3 else None
        cmdline_raw = parts[1] if len(parts) >= 4 else None
        cmdline = cmdline_raw.split() if cmdline_raw else None
        if not name:
            continue
        infos.append(
            ProcessInfo(
                pid=child_pid,
                name=name,
                exe=exe or None,
                cmdline=cmdline,
            )
        )
    return infos


# ---------------------------------------------------------------------------
# Visible-window detection
# ---------------------------------------------------------------------------


def detect_visible_window(pid: int) -> bool | None:
    """Return True if a visible top-level window is associated with *pid*.

    Uses ``EnumWindows`` + ``GetWindowThreadProcessId`` via ctypes on Windows.
    Returns None on non-Windows platforms.
    """
    if not _IS_WINDOWS:
        return None

    try:
        return _enum_windows_for_pid(pid)
    except Exception:  # noqa: BLE001
        _log.debug("EnumWindows failed for pid %d", pid, exc_info=True)
        return None


def _enum_windows_for_pid(pid: int) -> bool:
    """Walk all top-level windows and check if any belong to *pid*."""
    import ctypes
    import ctypes.wintypes

    user32 = ctypes.windll.user32  # type: ignore[attr-defined]

    # Callback type: BOOL CALLBACK EnumWindowsProc(HWND, LPARAM)
    WNDENUMPROC = ctypes.WINFUNCTYPE(  # noqa: N806
        ctypes.wintypes.BOOL,
        ctypes.wintypes.HWND,
        ctypes.wintypes.LPARAM,
    )

    found = [False]

    def _callback(hwnd: int, _lparam: int) -> bool:
        window_pid = ctypes.wintypes.DWORD()
        user32.GetWindowThreadProcessId(hwnd, ctypes.byref(window_pid))
        if window_pid.value == pid and user32.IsWindowVisible(hwnd):
            found[0] = True
            return False  # stop enumeration
        return True  # continue

    user32.EnumWindows(WNDENUMPROC(_callback), 0)
    return found[0]


# ---------------------------------------------------------------------------
# Console-host detection
# ---------------------------------------------------------------------------


def detect_console_host(pid: int) -> bool | None:
    """Return True if a console host is present in the process tree for *pid*.

    Looks for ``conhost.exe``, ``WindowsTerminal.exe``, or ``OpenConsole.exe``
    among the child processes.  Returns None on non-Windows platforms.
    """
    if not _IS_WINDOWS:
        return None

    try:
        children = get_process_tree(pid)
        return any(c.name.lower() in _CONSOLE_HOST_NAMES for c in children)
    except Exception:  # noqa: BLE001
        _log.debug("console host detection failed for pid %d", pid, exc_info=True)
        return None


# ---------------------------------------------------------------------------
# Creation flags (best-effort; not always available)
# ---------------------------------------------------------------------------


def get_creation_flags(pid: int) -> int | None:
    """Return the ``PROCESS_CREATION_FLAGS`` used when *pid* was created.

    This is only available via ``NtQueryInformationProcess`` and is best-effort.
    Returns None when it cannot be determined or on non-Windows.
    """
    if not _IS_WINDOWS:
        return None
    # Creation flags are not easily retrievable after process creation.
    # Returning None is the correct safe default; callers should infer
    # console behaviour from PE subsystem + observed console host presence.
    return None


# ---------------------------------------------------------------------------
# PE subsystem for a running process (convenience wrapper)
# ---------------------------------------------------------------------------


def get_process_pe_subsystem(exe_path: str | None) -> Subsystem | None:
    """Return the PE subsystem for *exe_path*, or None."""
    if exe_path is None:
        return None
    from launch_lab.inspect_pe import inspect_pe

    return inspect_pe(exe_path)
