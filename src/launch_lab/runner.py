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

import hashlib
import logging
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
from launch_lab.uv_provider import get_uv_binary, is_custom_uv_configured

logger = logging.getLogger(__name__)

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
    """Return uv version string, or None if uv is not available.

    When a custom uv binary has been configured via ``--custom-uv``, this
    queries the custom binary rather than the system ``uv``.
    """
    uv_bin = get_uv_binary("uv")
    try:
        result = subprocess.run(
            [uv_bin, "--version"],
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


def _uv_version_hash() -> str:
    """Return a short hash based on the effective uv version string.

    This is used to namespace the matrix venv cache directory so that
    different uv versions (or custom builds) each get their own venv.
    """
    ver = _uv_version() or "unknown"
    return hashlib.sha256(ver.encode()).hexdigest()[:10]


def _ensure_matrix_venv() -> Path:
    """Create (or reuse) a cached venv for ``venv-direct`` matrix scenarios.

    The venv is stored in ``.cache/matrix_venv_<uv-hash>/`` so that
    different uv versions each get an independent venv.  When a custom uv
    is configured the venv is **always** recreated (deleted then rebuilt)
    so that entrypoint wrappers are regenerated with the custom uv — this
    is critical for reproducing issues like the CUI-pythonw bug.

    Returns the venv root directory.
    """
    uv_hash = _uv_version_hash()
    cache_key = f"matrix_venv_{uv_hash}"

    if cache_key in _venv_provisioned:
        return _venv_provisioned[cache_key]

    uv_bin = get_uv_binary("uv")
    uv_ver = _uv_version() or "unknown"
    venv_dir = _CACHE_DIR / f"matrix_venv_{uv_hash}"
    scripts_dir = venv_dir / _SCRIPTS_DIR
    python_exe = scripts_dir / f"python{_EXE_SUFFIX}"

    logger.info(
        "Provisioning matrix venv  (uv=%s, hash=%s, dir=%s)",
        uv_ver,
        uv_hash,
        venv_dir,
    )

    # ----- Decide whether to (re)create the venv -----
    need_create = False

    if is_custom_uv_configured():
        if venv_dir.exists():
            logger.info(
                "Custom uv is active — removing existing venv to force "
                "re-creation of entrypoint wrappers: %s",
                venv_dir,
            )
            shutil.rmtree(venv_dir, ignore_errors=True)
        need_create = True
    elif not python_exe.exists():
        need_create = True

    # ----- Create the venv -----
    if need_create:
        _CACHE_DIR.mkdir(parents=True, exist_ok=True)
        logger.info(
            "Creating new venv with '%s venv %s' …",
            uv_bin,
            venv_dir,
        )
        subprocess.check_call([uv_bin, "venv", str(venv_dir)], timeout=60)
        logger.info("Venv created: %s", venv_dir)
    else:
        logger.info("Reusing existing venv: %s", venv_dir)

    # ----- Install fixture packages -----
    for pkg in ("pkg_console", "pkg_gui", "pkg_dual"):
        pkg_path = _FIXTURES_DIR / pkg
        if pkg_path.exists():
            logger.info(
                "Installing fixture package '%s' into venv (uv pip install --python %s %s) …",
                pkg,
                python_exe,
                pkg_path,
            )
            subprocess.check_call(
                [
                    uv_bin,
                    "pip",
                    "install",
                    "--python",
                    str(python_exe),
                    str(pkg_path),
                ],
                timeout=120,
            )
            logger.info("  ✓ %s installed", pkg)

    # ----- Log generated entrypoints for visibility -----
    if scripts_dir.exists():
        entrypoints = sorted(
            p.name for p in scripts_dir.iterdir() if p.is_file() and p.stem.startswith("lab-")
        )
        if entrypoints:
            logger.info(
                "Generated entrypoint wrappers in %s: %s",
                scripts_dir,
                ", ".join(entrypoints),
            )

    logger.info("Matrix venv ready: %s", venv_dir)
    _venv_provisioned[cache_key] = venv_dir
    return venv_dir


def provision_matrix_venv() -> Path:
    """Public wrapper for :func:`_ensure_matrix_venv`.

    Called by the CLI to eagerly provision the venv before the scenario
    loop begins so the user sees the venv-creation output as a distinct
    step.
    """
    return _ensure_matrix_venv()


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


def _is_uv_like(exe_path: str) -> bool:
    """Heuristically check if the executable is a uv / uvx / uvw binary."""
    stem = Path(exe_path).stem.lower()
    return stem in ("uv", "uvx", "uvw")


def _is_shim_like(exe_path: str) -> bool:
    """Check if the executable is the pyshim-win shim."""
    stem = Path(exe_path).stem.lower()
    return stem == "pyshim-win"


@dataclass
class _DetectionResult:
    """Window/console detection observations from Phase 1."""

    processes: list
    visible_window: bool | None = None
    console_window: bool | None = None
    creation_flags: int | None = None


def _build_keepalive_cmd(exe: str) -> list[str] | None:
    """Build a keepalive command for the given executable.

    Returns a command list that will keep the process alive for ~10 seconds
    so we can observe console/window behaviour, or None if no strategy is
    available.
    """
    if _is_python_like(exe):
        return [exe, "-c", "import time; time.sleep(10)"]
    if _is_uv_like(exe):
        # uv/uvx/uvw can run a Python sleep command
        return [exe, "run", "python", "-c", "import time; time.sleep(10)"]
    if _is_shim_like(exe):
        # Shim wraps python; delegate through the shim
        return [exe, "--hide-console", "--", "python", "-c", "import time; time.sleep(10)"]
    # For venv entrypoint wrappers (.exe in a Scripts/ or bin/ dir alongside
    # python.exe), use the sibling python interpreter as the keepalive.
    exe_path = Path(exe)
    if exe_path.suffix.lower() == ".exe" and exe_path.exists():
        sibling_python = exe_path.parent / f"python{_EXE_SUFFIX}"
        if sibling_python.exists():
            return [str(sibling_python), "-c", "import time; time.sleep(10)"]
    return None


def _detect_child_python_subsystem(exe: str) -> str | None:
    """For venv entrypoint wrappers, detect the PE subsystem of the child Python.

    Venv entrypoint wrappers (pip/uv generated .exe) internally launch the
    venv's python.exe or pythonw.exe.  The child interpreter's PE subsystem
    is what actually determines whether a console window appears.

    Returns the child interpreter's PE subsystem, or None if the exe is not
    a venv entrypoint wrapper.
    """
    exe_path = Path(exe)
    if not exe_path.suffix.lower() == ".exe" or not exe_path.exists():
        return None
    # Not a python interpreter or uv itself — likely a wrapper
    if _is_python_like(exe) or _is_uv_like(exe) or _is_shim_like(exe):
        return None
    scripts_dir = exe_path.parent
    # Check if this looks like a venv Scripts/ dir (has python.exe sibling)
    sibling_python = scripts_dir / f"python{_EXE_SUFFIX}"
    if not sibling_python.exists():
        return None
    # This is a venv entrypoint wrapper.  The wrapper uses either python.exe
    # or pythonw.exe depending on whether it's a console_scripts or gui_scripts
    # entry.  We check the actual PE of the interpreter that will be invoked.
    #
    # pip/uv gui_scripts wrappers call pythonw.exe; console_scripts call python.exe.
    # But in uv venvs, pythonw.exe is often a CUI copy (bug), so we need to
    # check the ACTUAL binary.
    wrapper_pe = inspect_pe(str(exe_path))
    if wrapper_pe == "GUI":
        # GUI wrapper → will invoke pythonw.exe
        pythonw = scripts_dir / f"pythonw{_EXE_SUFFIX}"
        if pythonw.exists():
            return inspect_pe(str(pythonw))
        # No pythonw → falls back to python.exe
        return inspect_pe(str(sibling_python))
    # CUI wrapper → invokes python.exe
    return inspect_pe(str(sibling_python))


def _try_keepalive_detection(exe: str) -> _DetectionResult | None:
    """Re-launch *exe* with a keepalive command for window/console detection.

    When a spawned process exits before we can snapshot its process tree and
    console host, this helper re-launches the executable with a long-lived
    command so we can still observe whether Windows allocates a console.

    Returns a :class:`_DetectionResult` on success, or ``None`` if no keepalive
    strategy is available for the executable.
    """
    keepalive_cmd = _build_keepalive_cmd(exe)
    if keepalive_cmd is None:
        return None

    try:
        ka_proc = subprocess.Popen(
            keepalive_cmd,
            creationflags=subprocess.CREATE_NEW_CONSOLE,
        )
    except (FileNotFoundError, OSError):
        return None

    time.sleep(0.8)  # Give extra time for process tree to stabilise
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
    try:
        ka_proc.kill()
    except OSError:
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
            for _ in range(10):
                time.sleep(0.05)
                if detect_proc.poll() is not None:
                    break
            else:
                time.sleep(0.3)

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

            # ---------------------------------------------------------
            # Inference fallback — fill in None values from PE subsystem
            # ---------------------------------------------------------
            # For venv entrypoint wrappers, the *child* interpreter's PE
            # subsystem determines console behaviour, not the wrapper's own.
            # A GUI wrapper that internally launches a CUI pythonw.exe
            # (e.g. uv venv bug) WILL produce a console window.
            effective_subsystem = pe_subsystem
            child_sub = _detect_child_python_subsystem(cmd[0])
            if child_sub is not None:
                # The child interpreter's subsystem overrides the wrapper's
                # for console detection purposes.
                effective_subsystem = child_sub

                # If the wrapper is GUI but the child is CUI, a console WILL
                # appear — override even if direct detection said False, because
                # the detection may have missed the conhost.exe due to timing.
                if pe_subsystem == "GUI" and child_sub == "CUI":
                    console_window = True

            if effective_subsystem is not None:
                if console_window is None:
                    console_window = effective_subsystem == "CUI"
                if visible_window is None:
                    if effective_subsystem == "CUI":
                        # CUI child process — console is typically visible
                        visible_window = False
                    else:
                        # True GUI child — check if this scenario creates
                        # a visible window (GUI entry-points do)
                        _mode_lower = scenario.mode.lower()
                        _sid_lower = scenario.scenario_id.lower()
                        if "gui" in _mode_lower or "gui" in _sid_lower:
                            visible_window = True
                        else:
                            visible_window = False

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

    When a custom uv has been configured via ``--custom-uv``, all
    ``uv`` / ``uvx`` / ``uvw`` launchers are resolved to the custom build
    directory.  For ``pyshim-win`` the binary lives inside the Cargo build
    tree.  Otherwise, if the binary is already on PATH it is returned
    unchanged.
    """
    # Custom uv override — resolve uv-family binaries from the provider.
    if launcher in ("uv", "uvx", "uvw") and is_custom_uv_configured():
        return get_uv_binary(launcher)

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
