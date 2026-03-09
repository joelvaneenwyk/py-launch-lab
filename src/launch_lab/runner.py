"""
Process runner for py-launch-lab.

Spawns child processes for a given scenario and collects observable facts:
- exit code
- stdout / stderr text
- timing

Windows-specific process tree and window detection is deferred to
detect_windows.py, which is only imported on win32.
"""

from __future__ import annotations

import shutil
import subprocess
import sys
from typing import Optional

from launch_lab.inspect_pe import inspect_pe
from launch_lab.matrix import Scenario
from launch_lab.models import LauncherKind, ScenarioResult


def _python_version() -> str:
    return f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}"


def _uv_version() -> Optional[str]:
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


def _parse_launcher(value: str) -> LauncherKind:
    """Safely convert a launcher string to a LauncherKind enum value."""
    try:
        return LauncherKind(value)
    except ValueError:
        return LauncherKind.UNKNOWN


def run_scenario(scenario: Scenario, timeout: float = 30.0) -> ScenarioResult:
    """
    Run a single scenario and return a ScenarioResult.

    This is the main entry point for M2+ execution.  At M0 (skeleton) it
    returns a placeholder result.
    """
    # TODO(M2): Implement full process observation
    uv_ver = _uv_version() if scenario.requires_uv else None

    cmd = _build_command(scenario)

    # M1: Resolve the actual executable and inspect its PE subsystem
    resolved_executable = shutil.which(cmd[0])
    pe_subsystem = inspect_pe(resolved_executable) if resolved_executable else None

    try:
        proc = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
        exit_code = proc.returncode
        stdout_text = proc.stdout or None
        stderr_text = proc.stderr or None
        stdout_available = proc.stdout is not None
        stderr_available = proc.stderr is not None
    except FileNotFoundError:
        exit_code = None
        stdout_text = None
        stderr_text = f"Executable not found: {cmd[0]}"
        stdout_available = False
        stderr_available = False
    except subprocess.TimeoutExpired:
        exit_code = None
        stdout_text = None
        stderr_text = f"Timed out after {timeout}s"
        stdout_available = False
        stderr_available = False

    return ScenarioResult(
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
        creation_flags=None,        # TODO(M2): capture on Windows
        stdout_available=stdout_available,
        stderr_available=stderr_available,
        visible_window_detected=None,   # TODO(M2): Windows-only
        console_window_detected=None,   # TODO(M2): Windows-only
        processes=[],                   # TODO(M2): Windows process tree
        exit_code=exit_code,
        stdout_text=stdout_text,
        stderr_text=stderr_text,
        notes=scenario.description,
    )


def _build_command(scenario: Scenario) -> list[str]:
    """Build the command list for a scenario."""
    return [scenario.launcher, *scenario.args]
