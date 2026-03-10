"""
Process runner for py-launch-lab.

Spawns child processes for a given scenario and collects observable facts:
- exit code
- stdout / stderr text
- PE subsystem of the resolved executable
- process tree snapshot (Windows)
- console-window and visible-window detection (Windows)

Windows-specific process tree and window detection is provided by
detect_windows.py, which is imported unconditionally but returns safe
defaults (None / empty list) on non-Windows platforms.
"""

from __future__ import annotations

import shutil
import subprocess
import sys
import time
from pathlib import Path

from launch_lab.collect import save_result
from launch_lab.detect_windows import (
    detect_console_host,
    detect_visible_window,
    get_creation_flags,
    get_process_tree,
)
from launch_lab.inspect_pe import inspect_pe
from launch_lab.matrix import Scenario
from launch_lab.models import LauncherKind, ScenarioResult


def _python_version() -> str:
    return f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}"


def _uv_version() -> str | None:
    """Return uv version string, or None if uv is not on PATH."""
    try:
        result = subprocess.run(
            ["uv", "--version"],
            capture_output=True,
            text=True,
            timeout=10,
        )
        if result.returncode == 0:
            return result.stdout.strip()
    except (FileNotFoundError, subprocess.TimeoutExpired):
        pass
    return None


def is_uv_available() -> bool:
    """Return True if ``uv`` is found on PATH and responds to ``--version``."""
    return _uv_version() is not None


def _parse_launcher(value: str) -> LauncherKind:
    """Safely convert a launcher string to a LauncherKind enum value."""
    try:
        return LauncherKind(value)
    except ValueError:
        return LauncherKind.UNKNOWN


def run_scenario(
    scenario: Scenario,
    timeout: float = 30.0,
    *,
    save_artifact: bool = False,
    artifact_dir: Path | None = None,
) -> ScenarioResult:
    """Run a single scenario and return a :class:`ScenarioResult`.

    When *save_artifact* is True the result JSON is written to *artifact_dir*
    (defaults to ``artifacts/json/``).
    """
    uv_ver = _uv_version() if scenario.requires_uv else None

    cmd = _build_command(scenario)

    # Resolve the actual executable and inspect its PE subsystem.
    # cmd[0] may already be an absolute path (from _resolve_launcher), so
    # check if it exists directly before falling back to shutil.which().
    _cmd0 = Path(cmd[0])
    resolved_executable = str(_cmd0) if _cmd0.is_file() else shutil.which(cmd[0])
    pe_subsystem = inspect_pe(resolved_executable) if resolved_executable else None

    # --- spawn and observe ---
    exit_code: int | None = None
    stdout_text: str | None = None
    stderr_text: str | None = None
    stdout_available: bool | None = None
    stderr_available: bool | None = None
    visible_window: bool | None = None
    console_window: bool | None = None
    creation_flags: int | None = None
    processes = []

    try:
        proc = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )

        # Brief pause to allow Windows to set up the process tree and
        # allocate console handles before we snapshot.
        time.sleep(0.3)

        # --- Windows-only observation while the child is still alive ---
        if proc.poll() is None:
            # Process is still running; collect live observations
            processes = get_process_tree(proc.pid)
            visible_window = detect_visible_window(proc.pid)
            console_window = detect_console_host(proc.pid)
            creation_flags = get_creation_flags(proc.pid)
        else:
            # Process finished very quickly; we can still attempt tree
            # queries but the child may already have exited.
            processes = get_process_tree(proc.pid)
            console_window = detect_console_host(proc.pid)

        # Wait for process to finish and capture output
        try:
            out, err = proc.communicate(timeout=timeout)
        except subprocess.TimeoutExpired:
            proc.kill()
            out, err = proc.communicate()

        exit_code = proc.returncode
        stdout_text = out or None
        stderr_text = err or None
        # True when the process actually produced output (not just "pipe was connected")
        stdout_available = bool(out)
        stderr_available = bool(err)

    except FileNotFoundError:
        exit_code = None
        stdout_text = None
        stderr_text = f"Executable not found: {cmd[0]}"
        stdout_available = False
        stderr_available = False

    result = ScenarioResult(
        scenario_id=scenario.scenario_id,
        platform=sys.platform,
        python_version=_python_version(),
        uv_version=uv_ver,
        launcher=_parse_launcher(scenario.launcher),
        mode=scenario.mode,
        fixture=scenario.fixture,
        resolved_executable=resolved_executable,
        resolved_kind=None,
        pe_subsystem=pe_subsystem,
        creation_flags=creation_flags,
        stdout_available=stdout_available,
        stderr_available=stderr_available,
        visible_window_detected=visible_window,
        console_window_detected=console_window,
        processes=processes,
        exit_code=exit_code,
        stdout_text=stdout_text,
        stderr_text=stderr_text,
        notes=scenario.description,
    )

    if save_artifact:
        kw = {"output_dir": artifact_dir} if artifact_dir else {}
        save_result(result, **kw)

    return result


def _resolve_launcher(launcher: str) -> str:
    """Resolve a launcher name to a full path if needed.

    For ``pyshim-win`` the binary lives inside the Cargo build tree and is
    not on PATH.  We look for it in the ``crates/pyshim-win/target``
    directory (release first, then debug).  If the binary is already on
    PATH we return it unchanged.
    """
    if shutil.which(launcher) is not None:
        return launcher

    if launcher == "pyshim-win":
        project_root = Path(__file__).resolve().parents[2]
        for profile in ("release", "debug"):
            candidate = (
                project_root / "crates" / "pyshim-win" / "target" / profile / "pyshim-win.exe"
            )
            if candidate.is_file():
                return str(candidate)

    return launcher


def _build_command(scenario: Scenario) -> list[str]:
    """Build the command list for a scenario."""
    return [_resolve_launcher(scenario.launcher), *scenario.args]
