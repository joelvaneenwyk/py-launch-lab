"""
Windows-specific process and window detection.

This module is imported unconditionally but is only meaningful on win32.
All public functions return safe defaults (None / empty list) on other
platforms so the rest of the codebase can use them without guards.

On Windows the implementation uses:
- ``ctypes`` with ``CreateToolhelp32Snapshot`` to walk the process tree.
- ``ctypes`` with ``user32.EnumWindows`` to detect visible top-level windows.
- Process tree inspection to detect ``conhost.exe`` presence.
"""

from __future__ import annotations

import logging
import sys

from launch_lab.models import ProcessInfo

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

    On Windows this uses ``CreateToolhelp32Snapshot`` via ctypes to enumerate
    child processes.  On other platforms an empty list is returned.
    """
    if not _IS_WINDOWS:
        return []

    try:
        return _get_process_tree_toolhelp(pid)
    except Exception:  # noqa: BLE001
        _log.debug("process tree query failed for pid %d", pid, exc_info=True)
        return []


def _get_process_tree_toolhelp(pid: int) -> list[ProcessInfo]:
    """Use ``CreateToolhelp32Snapshot`` to enumerate child processes of *pid*."""
    import ctypes
    import ctypes.wintypes

    # Constants
    TH32CS_SNAPPROCESS = 0x00000002
    INVALID_HANDLE_VALUE = ctypes.c_void_p(-1).value
    PROCESS_QUERY_LIMITED_INFORMATION = 0x1000

    class PROCESSENTRY32(ctypes.Structure):  # noqa: N801
        _fields_ = [
            ("dwSize", ctypes.wintypes.DWORD),
            ("cntUsage", ctypes.wintypes.DWORD),
            ("th32ProcessID", ctypes.wintypes.DWORD),
            ("th32DefaultHeapID", ctypes.POINTER(ctypes.c_ulong)),
            ("th32ModuleID", ctypes.wintypes.DWORD),
            ("cntThreads", ctypes.wintypes.DWORD),
            ("th32ParentProcessID", ctypes.wintypes.DWORD),
            ("pcPriClassBase", ctypes.c_long),
            ("dwFlags", ctypes.wintypes.DWORD),
            ("szExeFile", ctypes.c_char * 260),
        ]

    kernel32 = ctypes.windll.kernel32  # type: ignore[attr-defined]
    kernel32.CreateToolhelp32Snapshot.restype = ctypes.wintypes.HANDLE
    kernel32.CreateToolhelp32Snapshot.argtypes = [ctypes.wintypes.DWORD, ctypes.wintypes.DWORD]
    kernel32.OpenProcess.restype = ctypes.wintypes.HANDLE
    kernel32.OpenProcess.argtypes = [
        ctypes.wintypes.DWORD,
        ctypes.wintypes.BOOL,
        ctypes.wintypes.DWORD,
    ]
    kernel32.QueryFullProcessImageNameW.restype = ctypes.wintypes.BOOL
    kernel32.QueryFullProcessImageNameW.argtypes = [
        ctypes.wintypes.HANDLE,
        ctypes.wintypes.DWORD,
        ctypes.wintypes.LPWSTR,
        ctypes.POINTER(ctypes.wintypes.DWORD),
    ]
    kernel32.CloseHandle.restype = ctypes.wintypes.BOOL
    kernel32.CloseHandle.argtypes = [ctypes.wintypes.HANDLE]

    snapshot = kernel32.CreateToolhelp32Snapshot(TH32CS_SNAPPROCESS, 0)
    if snapshot == INVALID_HANDLE_VALUE:
        return []

    try:
        pe = PROCESSENTRY32()
        pe.dwSize = ctypes.sizeof(PROCESSENTRY32)

        infos: list[ProcessInfo] = []

        if not kernel32.Process32First(snapshot, ctypes.byref(pe)):
            return []

        while True:
            if pe.th32ParentProcessID == pid:
                name = pe.szExeFile.decode("utf-8", errors="replace")
                # Attempt to resolve full executable path via QueryFullProcessImageName.
                exe_path: str | None = None
                hproc = kernel32.OpenProcess(
                    PROCESS_QUERY_LIMITED_INFORMATION, False, pe.th32ProcessID
                )
                if hproc and hproc != INVALID_HANDLE_VALUE:
                    try:
                        # Start with a generous buffer; retry with a larger one
                        # if the path is longer than expected.
                        ERROR_INSUFFICIENT_BUFFER = 0x7A
                        buf_size = ctypes.wintypes.DWORD(1024)
                        buf = ctypes.create_unicode_buffer(buf_size.value)
                        if not kernel32.QueryFullProcessImageNameW(
                            hproc, 0, buf, ctypes.byref(buf_size)
                        ):
                            err = ctypes.get_last_error()
                            if err == ERROR_INSUFFICIENT_BUFFER:
                                # The path didn't fit — resize to what Windows reported.
                                buf = ctypes.create_unicode_buffer(buf_size.value)
                                if kernel32.QueryFullProcessImageNameW(
                                    hproc, 0, buf, ctypes.byref(buf_size)
                                ):
                                    exe_path = buf.value
                        else:
                            exe_path = buf.value
                    except Exception:  # noqa: BLE001
                        _log.debug(
                            "QueryFullProcessImageName failed for pid %d",
                            pe.th32ProcessID,
                            exc_info=True,
                        )
                    finally:
                        kernel32.CloseHandle(hproc)
                infos.append(
                    ProcessInfo(
                        pid=pe.th32ProcessID,
                        name=name,
                        exe=exe_path,
                        cmdline=None,
                    )
                )
            if not kernel32.Process32Next(snapshot, ctypes.byref(pe)):
                break

        return infos
    finally:
        kernel32.CloseHandle(snapshot)


# ---------------------------------------------------------------------------
# Visible-window detection
# ---------------------------------------------------------------------------


def detect_visible_window(pid: int) -> bool | None:
    """Return True if a visible top-level window is associated with *pid* or its children.

    Uses ``EnumWindows`` + ``GetWindowThreadProcessId`` via ctypes on Windows.
    Also checks direct child processes (e.g. ``conhost.exe``) because console
    windows are owned by the console host, not the child process itself.
    Returns None on non-Windows platforms.
    """
    if not _IS_WINDOWS:
        return None

    try:
        # Check windows for the process itself and all its direct children.
        # Console windows are owned by conhost.exe (a child), not the target pid.
        children = get_process_tree(pid)
        all_pids = {pid} | {c.pid for c in children}
        return _enum_windows_for_pids(all_pids)
    except Exception:  # noqa: BLE001
        _log.debug("EnumWindows failed for pid %d", pid, exc_info=True)
        return None


def _enum_windows_for_pids(pids: set[int]) -> bool:
    """Walk all top-level windows and check if any visible window belongs to *pids*."""
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
        if window_pid.value in pids and user32.IsWindowVisible(hwnd):
            found[0] = True
            return False  # stop enumeration
        return True  # continue

    user32.EnumWindows.argtypes = [WNDENUMPROC, ctypes.wintypes.LPARAM]
    user32.EnumWindows.restype = ctypes.wintypes.BOOL

    ret = user32.EnumWindows(WNDENUMPROC(_callback), 0)

    # EnumWindows returns 0 both on early callback termination and on real
    # errors.  If we found a window the early exit is expected; otherwise
    # check GetLastError to distinguish a genuine failure.
    if ret == 0 and not found[0]:
        err = ctypes.get_last_error()
        if err != 0:
            _log.debug("EnumWindows returned error code %d for pids %s", err, pids)

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
