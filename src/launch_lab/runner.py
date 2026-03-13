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

import platform
import shutil
import subprocess
import sys
import time
from dataclasses import dataclass
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

# ---------------------------------------------------------------------------
# Project paths
# ---------------------------------------------------------------------------

_PROJECT_ROOT = Path(__file__).resolve().parents[2]
_FIXTURES_DIR = _PROJECT_ROOT / "fixtures"
_CACHE_DIR = _PROJECT_ROOT / ".cache"

_IS_WINDOWS = sys.platform == "win32"
_SCRIPTS_DIR = "Scripts" if _IS_WINDOWS else "bin"
_EXE_SUFFIX = ".exe" if _IS_WINDOWS else ""


def _os_version() -> str:
    """Return a detailed OS version string (e.g. 'Windows-10-10.0.22631-SP0')."""
    return platform.platform()


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


# ---------------------------------------------------------------------------
# Venv provisioning for venv-direct scenarios
# ---------------------------------------------------------------------------

# Cache to avoid recreating the venv for every scenario in a single run.
_venv_provisioned: dict[str, Path] = {}


def _ensure_matrix_venv() -> Path:
    """Create (or reuse) a cached venv for ``venv-direct`` matrix scenarios.

    The venv is created in ``.cache/matrix_venv/`` within the project root
    using ``uv venv``.  All fixture packages (pkg_console, pkg_gui, pkg_dual)
    are installed into it.

    Returns the venv root directory.
    """
    cache_key = "matrix_venv"
    if cache_key in _venv_provisioned:
        return _venv_provisioned[cache_key]

    venv_dir = _CACHE_DIR / "matrix_venv"
    scripts_dir = venv_dir / _SCRIPTS_DIR
    python_exe = scripts_dir / f"python{_EXE_SUFFIX}"

    # Create the venv if the python executable is missing.
    if not python_exe.exists():
        _CACHE_DIR.mkdir(parents=True, exist_ok=True)
        subprocess.check_call(["uv", "venv", str(venv_dir)], timeout=60)

    # Install fixture packages (idempotent — uv pip handles re-installs).
    for pkg in ("pkg_console", "pkg_gui", "pkg_dual"):
        pkg_path = _FIXTURES_DIR / pkg
        if pkg_path.exists():
            subprocess.check_call(
                [
                    "uv",
                    "pip",
                    "install",
                    "--python",
                    str(python_exe),
                    str(pkg_path),
                ],
                timeout=120,
            )

    _venv_provisioned[cache_key] = venv_dir
    return venv_dir


def _build_venv_command(scenario: Scenario) -> list[str]:
    """Build the command list for a ``venv-direct`` scenario.

    Provisions the shared matrix venv (if needed) and maps each scenario to
    the correct executable + arguments.
    """
    venv_dir = _ensure_matrix_venv()
    scripts_dir = venv_dir / _SCRIPTS_DIR

    sid = scenario.scenario_id

    if sid == "venv-python-script-py":
        exe = str(scripts_dir / f"python{_EXE_SUFFIX}")
        script = str(_FIXTURES_DIR / "raw_py" / "hello.py")
        return [exe, script]

    if sid == "venv-pythonw-script-py":
        exe = str(scripts_dir / f"pythonw{_EXE_SUFFIX}")
        script = str(_FIXTURES_DIR / "raw_py" / "hello.py")
        return [exe, script]

    if sid == "venv-console-entrypoint":
        return [str(scripts_dir / f"lab-console{_EXE_SUFFIX}")]

    if sid == "venv-gui-entrypoint":
        return [str(scripts_dir / f"lab-gui{_EXE_SUFFIX}")]

    if sid == "venv-dual-console-entrypoint":
        return [str(scripts_dir / f"lab-dual-console{_EXE_SUFFIX}")]

    if sid == "venv-dual-gui-entrypoint":
        return [str(scripts_dir / f"lab-dual-gui{_EXE_SUFFIX}")]

    # Fallback: try running with the venv python.
    return [str(scripts_dir / f"python{_EXE_SUFFIX}"), *scenario.args]


def _is_python_like(exe_path: str) -> bool:
    """Heuristically check if the executable looks like a Python interpreter."""
    stem = Path(exe_path).stem.lower()
    return stem in (
        "python",
        "python3",
        "pythonw",
        "pythonw3",
    ) or stem.startswith(("python3.", "pythonw3."))


@dataclass
class _DetectionResult:
    """Window/console detection observations from Phase 1."""

    processes: list
    visible_window: bool | None = None
    console_window: bool | None = None
    creation_flags: int | None = None


def _try_keepalive_detection(exe: str) -> _DetectionResult | None:
    """Re-launch *exe* with a keepalive command for window/console detection.

    When a spawned process exits before we can snapshot its process tree and
    console host, this helper re-launches the executable with a long-lived
    command so we can still observe whether Windows allocates a console.

    Returns a :class:`_DetectionResult` on success, or ``None`` if no keepalive
    strategy is available for the executable.
    """
    if _is_python_like(exe):
        keepalive_cmd = [exe, "-c", "import time; time.sleep(10)"]
    else:
        return None

    ka_proc = subprocess.Popen(
        keepalive_cmd,
        creationflags=subprocess.CREATE_NEW_CONSOLE,
    )
    time.sleep(0.5)
    try:
        if ka_proc.poll() is None:
            result = _DetectionResult(
                processes=get_process_tree(ka_proc.pid),
                visible_window=detect_visible_window(ka_proc.pid),
                console_window=detect_console_host(ka_proc.pid),
                creation_flags=get_creation_flags(ka_proc.pid),
            )
            ka_proc.kill()
            ka_proc.wait()
            return result
    except Exception:  # noqa: BLE001
        pass
    ka_proc.wait()
    return None


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
    uv_ver = _uv_version()

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
        # ----------------------------------------------------------------
        # Phase 1 — Window / console detection (Windows only)
        # Launch with CREATE_NEW_CONSOLE and *no pipes* so Windows
        # allocates a real console.  Pipes suppress console allocation,
        # which would otherwise cause detect_visible_window / console_host
        # to always return False for CUI executables.
        # ----------------------------------------------------------------
        if _IS_WINDOWS:
            detect_proc = subprocess.Popen(
                cmd,
                creationflags=subprocess.CREATE_NEW_CONSOLE,
                # No stdout/stderr pipes — process gets its own console.
            )

            # Poll aggressively for fast-exiting processes.
            for _ in range(6):
                time.sleep(0.05)
                if detect_proc.poll() is not None:
                    break
            else:
                time.sleep(0.2)

            if detect_proc.poll() is None:
                processes = get_process_tree(detect_proc.pid)
                visible_window = detect_visible_window(detect_proc.pid)
                console_window = detect_console_host(detect_proc.pid)
                creation_flags = get_creation_flags(detect_proc.pid)
                detect_proc.kill()
                detect_proc.wait()
            else:
                detect_proc.wait()
                # Process exited too quickly — console host is already gone.
                # Re-launch the bare executable with a keepalive if possible
                # so we can still observe console/window behaviour.
                det = _try_keepalive_detection(cmd[0])
                if det is not None:
                    processes = det.processes
                    visible_window = det.visible_window
                    console_window = det.console_window
                    creation_flags = det.creation_flags

        # ----------------------------------------------------------------
        # Phase 2 — Output capture (always)
        # Run again with pipes to collect stdout/stderr and exit code.
        # ----------------------------------------------------------------
        proc = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )

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
        os_version=_os_version(),
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
        command_line=cmd,
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
    if scenario.launcher == "venv-direct":
        return _build_venv_command(scenario)
    return [_resolve_launcher(scenario.launcher), *scenario.args]
