"""
Integration tests: venv python/pythonw executables and entrypoint scripts.

These tests create virtual environments using ``uv venv``, install fixture
packages into them, and verify observable behaviour against the *ideal*
expectations defined in ``launch_lab.expectations.EXPECTATIONS`` (the single
source of truth for expected Windows launch semantics).

Where current tooling (e.g. ``uv venv``) produces behaviour that deviates from
the ideal expectation, ``KNOWN_DEVIATIONS`` is consulted and the test uses
``pytest.xfail`` rather than asserting the buggy value.  When the upstream fix
lands, the xfail turns into xpass — automatic signal that the deviation is
resolved.

Covered areas:

1. **venv python / pythonw executables**
   - On Windows the venv ``python.exe`` is a CUI (console-subsystem) copy or
     symlink of the base interpreter.  It should behave identically to the
     system ``python.exe``: allocate a console window and produce stdout.
   - The venv ``pythonw.exe`` is the GUI-subsystem counterpart.  It should
     **not** allocate a console window.
   - File sizes and PE subsystems are compared against the system interpreter
     to document how venv executables relate to their originals.

2. **project.scripts (console entrypoints)**
   - ``pip install`` (or the equivalent) generates a small ``.exe`` wrapper on
     Windows for each ``[project.scripts]`` entry.  That wrapper is a CUI
     executable and should create a console window.

3. **project.gui-scripts (GUI entrypoints)**
   - ``[project.gui-scripts]`` wrappers are GUI-subsystem executables on
     Windows.  They should **not** allocate a console window.

4. **Dual packages (both project.scripts and project.gui-scripts)**
   - A single package may expose both console and GUI entrypoints.  The tests
     verify that the correct subsystem is used for each.

On non-Windows platforms the PE-subsystem and console-window assertions are
skipped; the tests still verify that the venv can be created, packages can be
installed, and the entrypoints execute successfully.

Virtual environments are created in ``.cache/test_venv_<id>/`` within the
project root using ``uv venv`` for speed and reproducibility.

See also
--------
- ``docs/scenario-matrix.md`` — human-readable scenario table
- ``src/launch_lab/matrix.py`` — formal scenario definitions
- ``src/launch_lab/expectations.py`` — ideal expectations (single source of truth)
"""

from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path

import pytest

from launch_lab.expectations import EXPECTATIONS, is_known_deviation
from launch_lab.inspect_pe import inspect_pe
from launch_lab.matrix import Scenario
from launch_lab.models import LauncherKind
from launch_lab.runner import run_scenario

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------

_PROJECT_ROOT = Path(__file__).resolve().parents[2]
_FIXTURES = _PROJECT_ROOT / "fixtures"
_CACHE_DIR = _PROJECT_ROOT / ".cache"

_IS_WINDOWS = sys.platform == "win32"

# On Windows the venv Scripts dir is ``Scripts/``; elsewhere ``bin/``.
_SCRIPTS_DIR = "Scripts" if _IS_WINDOWS else "bin"
_EXE_SUFFIX = ".exe" if _IS_WINDOWS else ""


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _uv_available() -> bool:
    """Return True if ``uv`` is on PATH."""
    return shutil.which("uv") is not None


def _create_uv_venv(venv_path: Path) -> None:
    """Create a virtual environment using ``uv venv``.

    If the venv already exists it is removed first to guarantee a clean state.
    """
    if venv_path.exists():
        shutil.rmtree(venv_path)
    venv_path.parent.mkdir(parents=True, exist_ok=True)
    subprocess.check_call(
        ["uv", "venv", str(venv_path)],
        timeout=60,
    )


def _uv_pip_install(venv_python: Path, *packages: str | Path) -> None:
    """Install packages into a venv using ``uv pip install``."""
    subprocess.check_call(
        [
            "uv",
            "pip",
            "install",
            "--python",
            str(venv_python),
            *[str(p) for p in packages],
        ],
        timeout=120,
    )


def _make_venv_scenario(
    scenario_id: str,
    launcher_path: str,
    args: list[str],
    *,
    fixture: str = "raw_py",
    mode: str = "",
    description: str = "",
) -> Scenario:
    """Build a Scenario that uses a venv executable as the launcher."""
    return Scenario(
        scenario_id=scenario_id,
        launcher=launcher_path,
        mode=mode or scenario_id,
        fixture=fixture,
        args=args,
        description=description,
    )


# ---------------------------------------------------------------------------
# Fixtures (pytest)
# ---------------------------------------------------------------------------

# Guard: all tests in this module require uv.
pytestmark = pytest.mark.skipif(not _uv_available(), reason="uv not available on PATH")


@pytest.fixture(scope="module")
def venv_dir() -> Path:
    """Create a fresh virtual environment shared by all tests in this module.

    The venv is created once using ``uv venv`` in ``.cache/test_venv_0/``
    within the project root and reused across test functions.
    """
    venv_path = _CACHE_DIR / "test_venv_0"
    _create_uv_venv(venv_path)
    return venv_path


@pytest.fixture(scope="module")
def venv_python(venv_dir: Path) -> Path:
    """Return the path to the venv's ``python`` executable."""
    exe = venv_dir / _SCRIPTS_DIR / f"python{_EXE_SUFFIX}"
    assert exe.exists(), f"venv python not found: {exe}"
    return exe


@pytest.fixture(scope="module")
def venv_with_packages(venv_dir: Path, venv_python: Path) -> Path:
    """Install all fixture packages into the venv and return venv_dir.

    Installs: pkg_console, pkg_gui, pkg_dual — using ``uv pip install``.
    """
    for pkg in ("pkg_console", "pkg_gui", "pkg_dual"):
        pkg_path = _FIXTURES / pkg
        _uv_pip_install(venv_python, pkg_path)
    return venv_dir


# ===================================================================
# 0. venv python vs system python — comparison tests
# ===================================================================


class TestVenvVsSystemPython:
    """Compare venv python/pythonw against the system interpreter.

    These tests document the relationship between venv executables and the
    system originals: file sizes, PE subsystems, and whether the venv copies
    are identical or symlinked.
    """

    def test_system_python_exists(self) -> None:
        """Sanity: sys.executable should point to an existing file."""
        assert Path(sys.executable).is_file(), f"sys.executable not found: {sys.executable}"

    def test_venv_python_file_info(self, venv_python: Path) -> None:
        """Document the venv python size alongside the system python size."""
        system_python = Path(sys.executable)
        venv_size = venv_python.stat().st_size
        sys_size = system_python.stat().st_size
        # Log sizes for documentation purposes (visible in pytest -v -s output)
        print(f"\n  system python: {system_python} ({sys_size:,} bytes)")
        print(f"  venv python:   {venv_python} ({venv_size:,} bytes)")
        # On Windows, venv python.exe is typically a copy; sizes may differ
        # slightly or be identical.  With ``uv venv`` the venv python may
        # be a hardlink or thin copy.
        assert venv_size > 0, "venv python should not be empty"
        assert sys_size > 0, "system python should not be empty"

    @pytest.mark.skipif(not _IS_WINDOWS, reason="PE comparison only meaningful on Windows")
    def test_venv_python_pe_matches_system(self, venv_python: Path) -> None:
        """Both venv and system python.exe should be CUI executables."""
        system_python = Path(sys.executable)
        sys_pe = inspect_pe(system_python)
        venv_pe = inspect_pe(venv_python)
        print(f"\n  system python PE subsystem: {sys_pe}")
        print(f"  venv python PE subsystem:   {venv_pe}")
        assert venv_pe == "CUI", f"venv python should be CUI, got {venv_pe}"
        assert sys_pe == "CUI", f"system python should be CUI, got {sys_pe}"

    @pytest.mark.skipif(not _IS_WINDOWS, reason="pythonw only on Windows")
    def test_venv_pythonw_file_info(self, venv_dir: Path) -> None:
        """Document the venv pythonw size alongside the system pythonw."""
        venv_pythonw = venv_dir / _SCRIPTS_DIR / "pythonw.exe"
        # Find system pythonw next to system python
        sys_dir = Path(sys.executable).parent
        sys_pythonw = sys_dir / "pythonw.exe"

        assert venv_pythonw.is_file(), f"venv pythonw not found: {venv_pythonw}"

        venv_size = venv_pythonw.stat().st_size
        print(f"\n  venv pythonw: {venv_pythonw} ({venv_size:,} bytes)")
        if sys_pythonw.is_file():
            sys_size = sys_pythonw.stat().st_size
            print(f"  system pythonw: {sys_pythonw} ({sys_size:,} bytes)")
        else:
            print(f"  system pythonw: NOT FOUND at {sys_pythonw}")

        assert venv_size > 0, "venv pythonw should not be empty"

    @pytest.mark.skipif(not _IS_WINDOWS, reason="PE comparison only meaningful on Windows")
    def test_venv_pythonw_pe_matches_system(self, venv_dir: Path) -> None:
        """The venv pythonw.exe should be GUI-subsystem, matching the system pythonw.

        Expectations source: ``EXPECTATIONS["venv-pythonw-script-py"]``
        """
        venv_pythonw = venv_dir / _SCRIPTS_DIR / "pythonw.exe"
        sys_pythonw = Path(sys.executable).parent / "pythonw.exe"

        venv_pe = inspect_pe(venv_pythonw)
        print(f"\n  venv pythonw PE subsystem: {venv_pe}")

        expected = EXPECTATIONS["venv-pythonw-script-py"]
        ideal_pe = expected.pe_subsystem

        # System pythonw should always be GUI
        if sys_pythonw.is_file():
            sys_pe = inspect_pe(sys_pythonw)
            print(f"  system pythonw PE subsystem: {sys_pe}")
            assert sys_pe == "GUI", f"system pythonw should be GUI, got {sys_pe}"

        # Check venv pythonw against the ideal expectation
        deviation = is_known_deviation("venv-pythonw-script-py", "pe_subsystem")
        if venv_pe != ideal_pe and deviation is not None:
            pytest.xfail(
                f"Known deviation: venv pythonw is {venv_pe} instead of {ideal_pe}.  "
                f"{deviation.reason}"
            )
        assert venv_pe == ideal_pe, f"Expected venv pythonw to be {ideal_pe}, got {venv_pe}."

    @pytest.mark.skipif(not _IS_WINDOWS, reason="Symlink/hardlink checks Windows-specific")
    def test_venv_python_is_copy_or_link(self, venv_python: Path) -> None:
        """Document whether the venv python is a copy, symlink, or hardlink."""
        system_python = Path(sys.executable)
        is_symlink = venv_python.is_symlink()
        # Check hardlink by comparing inode/file-id
        try:
            venv_stat = venv_python.stat()
            sys_stat = system_python.stat()
            same_file = venv_stat.st_dev == sys_stat.st_dev and venv_stat.st_ino == sys_stat.st_ino
        except OSError:
            same_file = False

        if is_symlink:
            link_target = venv_python.resolve()
            print(f"\n  venv python is a SYMLINK -> {link_target}")
        elif same_file:
            print("\n  venv python is a HARDLINK (same inode as system python)")
        else:
            print("\n  venv python is a COPY (independent file)")
        # No assertion — just documenting the relationship

    def test_venv_python_version_matches(self, venv_python: Path) -> None:
        """The venv python should report the same version as the system python."""
        result = subprocess.run(
            [str(venv_python), "--version"],
            capture_output=True,
            text=True,
            timeout=10,
        )
        assert result.returncode == 0
        venv_version = result.stdout.strip()
        sys_version = (
            f"Python {sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}"
        )
        print(f"\n  system: {sys_version}")
        print(f"  venv:   {venv_version}")
        assert sys_version in venv_version, (
            f"Version mismatch: system={sys_version}, venv={venv_version}"
        )


# ===================================================================
# 1. venv python executable
# ===================================================================


class TestVenvPython:
    """Tests for the venv's ``python`` executable."""

    def test_venv_python_exists(self, venv_python: Path) -> None:
        """The venv must contain a python executable."""
        assert venv_python.is_file()

    def test_venv_python_runs_script(self, venv_python: Path) -> None:
        """The venv python should be able to run a simple script."""
        script = _FIXTURES / "raw_py" / "hello.py"
        scenario = _make_venv_scenario(
            "venv-python-script-py",
            str(venv_python),
            [str(script)],
            description="venv python hello.py",
        )
        result = run_scenario(scenario, timeout=15)
        assert result.exit_code == 0
        assert result.stdout_available is True
        assert result.stdout_text is not None
        assert "hello from raw_py/hello.py" in result.stdout_text

    @pytest.mark.skipif(not _IS_WINDOWS, reason="PE inspection only meaningful on Windows")
    def test_venv_python_is_cui(self, venv_python: Path) -> None:
        """On Windows the venv python.exe must be a CUI executable.

        The venv copies (or symlinks) the base interpreter's ``python.exe``
        which is a console-subsystem (CUI) PE binary.  This means that
        launching it will allocate a console window — the expected behaviour
        for console scripts.
        """
        subsystem = inspect_pe(venv_python)
        assert subsystem == "CUI", (
            f"Expected venv python to be CUI, got {subsystem}. "
            "The venv python.exe should be a console-subsystem executable."
        )

    @pytest.mark.skipif(not _IS_WINDOWS, reason="Console detection only meaningful on Windows")
    def test_venv_python_console_window(self, venv_python: Path) -> None:
        """On Windows the venv python should produce a console window.

        Because venv ``python.exe`` is a CUI binary, Windows allocates a
        console (conhost.exe / Windows Terminal) for it.
        """
        script = _FIXTURES / "raw_py" / "hello.py"
        scenario = _make_venv_scenario(
            "venv-python-console-check",
            str(venv_python),
            [str(script)],
        )
        result = run_scenario(scenario, timeout=15)
        assert result.exit_code == 0
        # Console window detection is best-effort.  Short-lived processes
        # may exit before the process tree can be observed, causing
        # console_window_detected to be False even though a console existed.
        # Only assert when we actually captured process tree entries.
        if result.console_window_detected is not None and result.processes:
            assert result.console_window_detected is True, (
                "venv python.exe (CUI) should create a console window"
            )

    def test_venv_python_no_pe_on_non_windows(self, venv_python: Path) -> None:
        """On non-Windows, PE inspection should return NOT_PE or None."""
        if _IS_WINDOWS:
            pytest.skip("Only meaningful on non-Windows")
        subsystem = inspect_pe(venv_python)
        assert subsystem in (None, "NOT_PE"), (
            f"Expected None or NOT_PE on non-Windows, got {subsystem}"
        )

    def test_venv_python_result_fields(self, venv_python: Path) -> None:
        """The ScenarioResult should have all expected fields populated."""
        script = _FIXTURES / "raw_py" / "hello.py"
        scenario = _make_venv_scenario(
            "venv-python-fields-check",
            str(venv_python),
            [str(script)],
        )
        result = run_scenario(scenario, timeout=15)
        assert result.platform == sys.platform
        assert result.python_version
        assert result.resolved_executable is not None
        assert result.launcher == LauncherKind.UNKNOWN  # custom path, not a standard launcher


# ===================================================================
# 2. venv pythonw executable (Windows-only)
# ===================================================================


class TestVenvPythonW:
    """Tests for the venv's ``pythonw`` executable (Windows-only)."""

    @pytest.mark.skipif(not _IS_WINDOWS, reason="pythonw only exists on Windows")
    def test_venv_pythonw_exists(self, venv_dir: Path) -> None:
        """On Windows the venv must contain a pythonw.exe."""
        pythonw = venv_dir / _SCRIPTS_DIR / "pythonw.exe"
        assert pythonw.is_file(), f"venv pythonw not found: {pythonw}"

    @pytest.mark.skipif(not _IS_WINDOWS, reason="pythonw only exists on Windows")
    def test_venv_pythonw_subsystem(self, venv_dir: Path) -> None:
        """The venv pythonw.exe should be a GUI-subsystem binary.

        Expectations source: ``EXPECTATIONS["venv-pythonw-script-py"]``

        The ideal behaviour is for the venv ``pythonw.exe`` to be a genuine
        GUI PE binary — matching the system ``pythonw.exe``.  If it is CUI
        instead (as ``uv venv`` currently produces), this is a known
        deviation that is documented in ``KNOWN_DEVIATIONS``.
        """
        pythonw = venv_dir / _SCRIPTS_DIR / "pythonw.exe"
        subsystem = inspect_pe(pythonw)
        print(f"\n  venv pythonw PE subsystem: {subsystem}")

        expected = EXPECTATIONS["venv-pythonw-script-py"]
        ideal_pe = expected.pe_subsystem

        deviation = is_known_deviation("venv-pythonw-script-py", "pe_subsystem")
        if subsystem != ideal_pe and deviation is not None:
            pytest.xfail(
                f"Known deviation: venv pythonw is {subsystem} instead of {ideal_pe}.  "
                f"{deviation.reason}"
            )
        assert subsystem == ideal_pe, f"Expected venv pythonw to be {ideal_pe}, got {subsystem}."

    @pytest.mark.skipif(not _IS_WINDOWS, reason="pythonw only exists on Windows")
    def test_venv_pythonw_runs_script(self, venv_dir: Path) -> None:
        """pythonw should be able to run a script (no stdout expected)."""
        pythonw = venv_dir / _SCRIPTS_DIR / "pythonw.exe"
        script = _FIXTURES / "raw_py" / "hello.py"
        scenario = _make_venv_scenario(
            "venv-pythonw-script-py",
            str(pythonw),
            [str(script)],
            fixture="raw_py",
            description="venv pythonw hello.py",
        )
        result = run_scenario(scenario, timeout=15)
        assert result.exit_code == 0

    @pytest.mark.skipif(not _IS_WINDOWS, reason="pythonw only exists on Windows")
    def test_venv_pythonw_console_window(self, venv_dir: Path) -> None:
        """The venv pythonw.exe should NOT create a console window.

        Expectations source: ``EXPECTATIONS["venv-pythonw-script-py"]``

        pythonw.exe is a GUI-subsystem binary and should not allocate a
        console.  If the venv tooling creates a CUI trampoline instead,
        a console window will appear — this is a known deviation.
        """
        pythonw = venv_dir / _SCRIPTS_DIR / "pythonw.exe"
        script = _FIXTURES / "raw_py" / "hello.py"
        scenario = _make_venv_scenario(
            "venv-pythonw-console-check",
            str(pythonw),
            [str(script)],
            description="venv pythonw hello.py — verify no console window",
        )
        result = run_scenario(scenario, timeout=15)

        expected = EXPECTATIONS["venv-pythonw-script-py"]
        if result.console_window_detected is not None:
            deviation = is_known_deviation("venv-pythonw-script-py", "console_window")
            if result.console_window_detected != expected.console_window and deviation is not None:
                pytest.xfail(
                    f"Known deviation: console_window={result.console_window_detected}, "
                    f"ideal={expected.console_window}.  {deviation.reason}"
                )
            assert result.console_window_detected == expected.console_window, (
                f"venv pythonw.exe console_window: expected {expected.console_window}, "
                f"got {result.console_window_detected}"
            )

    def test_venv_pythonw_absent_on_non_windows(self, venv_dir: Path) -> None:
        """On non-Windows there is no pythonw executable in the venv."""
        if _IS_WINDOWS:
            pytest.skip("Only meaningful on non-Windows")
        pythonw = venv_dir / _SCRIPTS_DIR / "pythonw"
        assert not pythonw.exists(), "pythonw should not exist on non-Windows"


# ===================================================================
# 3. project.scripts — console entrypoints in venv
# ===================================================================


class TestVenvConsoleEntrypoint:
    """Tests for ``[project.scripts]`` (console) entrypoints installed in a venv.

    When a package with ``[project.scripts]`` is pip-installed into a venv,
    pip generates a small wrapper executable for each entry.  On Windows
    these wrappers are CUI ``.exe`` files that allocate a console window.
    """

    def test_console_entrypoint_exists(self, venv_with_packages: Path) -> None:
        """The console entrypoint wrapper should be created by pip install."""
        wrapper = venv_with_packages / _SCRIPTS_DIR / f"lab-console{_EXE_SUFFIX}"
        assert wrapper.is_file(), f"Console entrypoint not found: {wrapper}"

    def test_console_entrypoint_runs(self, venv_with_packages: Path) -> None:
        """The console entrypoint should execute and produce stdout."""
        wrapper = venv_with_packages / _SCRIPTS_DIR / f"lab-console{_EXE_SUFFIX}"
        scenario = _make_venv_scenario(
            "venv-console-entrypoint",
            str(wrapper),
            [],
            fixture="pkg_console",
            description="venv console entrypoint (project.scripts)",
        )
        result = run_scenario(scenario, timeout=15)
        assert result.exit_code == 0
        assert result.stdout_available is True
        assert result.stdout_text is not None
        assert "hello from lab-console" in result.stdout_text

    @pytest.mark.skipif(not _IS_WINDOWS, reason="PE inspection only meaningful on Windows")
    def test_console_entrypoint_is_cui(self, venv_with_packages: Path) -> None:
        """On Windows the console entrypoint wrapper must be a CUI executable.

        pip generates CUI wrappers for ``[project.scripts]`` entries.  This
        ensures that the script inherits or creates a console window, which
        is the correct behaviour for command-line tools.
        """
        wrapper = venv_with_packages / _SCRIPTS_DIR / "lab-console.exe"
        subsystem = inspect_pe(wrapper)
        assert subsystem == "CUI", (
            f"Expected console entrypoint to be CUI, got {subsystem}. "
            "project.scripts wrappers should be console-subsystem executables."
        )

    @pytest.mark.skipif(not _IS_WINDOWS, reason="PE inspection only meaningful on Windows")
    def test_console_entrypoint_file_info(self, venv_with_packages: Path) -> None:
        """Document the console entrypoint wrapper size and PE details."""
        wrapper = venv_with_packages / _SCRIPTS_DIR / f"lab-console{_EXE_SUFFIX}"
        size = wrapper.stat().st_size
        pe = inspect_pe(wrapper) if _IS_WINDOWS else None
        print(f"\n  lab-console wrapper: {wrapper} ({size:,} bytes, PE={pe})")
        assert size > 0

    @pytest.mark.skipif(not _IS_WINDOWS, reason="Console detection only meaningful on Windows")
    def test_console_entrypoint_console_window(self, venv_with_packages: Path) -> None:
        """The console entrypoint (CUI) should create a console window."""
        wrapper = venv_with_packages / _SCRIPTS_DIR / "lab-console.exe"
        scenario = _make_venv_scenario(
            "venv-console-ep-window",
            str(wrapper),
            [],
            fixture="pkg_console",
        )
        result = run_scenario(scenario, timeout=15)
        assert result.exit_code == 0
        # Only assert when the process tree was observable.
        if result.console_window_detected is not None and result.processes:
            assert result.console_window_detected is True, (
                "project.scripts entrypoint (CUI) should create a console window"
            )

    def test_console_entrypoint_artifact(self, venv_with_packages: Path, tmp_path: Path) -> None:
        """The result should serialise to a valid JSON artifact."""
        wrapper = venv_with_packages / _SCRIPTS_DIR / f"lab-console{_EXE_SUFFIX}"
        scenario = _make_venv_scenario(
            "venv-console-entrypoint",
            str(wrapper),
            [],
            fixture="pkg_console",
        )
        result = run_scenario(scenario, timeout=15, save_artifact=True, artifact_dir=tmp_path)
        artifact = tmp_path / f"{result.scenario_id}.json"
        assert artifact.exists()


# ===================================================================
# 4. project.gui-scripts — GUI entrypoints in venv
# ===================================================================


class TestVenvGuiEntrypoint:
    """Tests for ``[project.gui-scripts]`` (GUI) entrypoints installed in a venv.

    When a package with ``[project.gui-scripts]`` is pip-installed into a
    venv, pip generates a GUI-subsystem ``.exe`` wrapper on Windows.  This
    wrapper does **not** allocate a console window.
    """

    @pytest.mark.skipif(not _IS_WINDOWS, reason="GUI entrypoints produce .exe only on Windows")
    def test_gui_entrypoint_exists(self, venv_with_packages: Path) -> None:
        """The GUI entrypoint wrapper should be created by pip install."""
        wrapper = venv_with_packages / _SCRIPTS_DIR / "lab-gui.exe"
        assert wrapper.is_file(), f"GUI entrypoint not found: {wrapper}"

    @pytest.mark.skipif(not _IS_WINDOWS, reason="GUI entrypoint .exe only on Windows")
    def test_gui_entrypoint_is_gui(self, venv_with_packages: Path) -> None:
        """On Windows the GUI entrypoint wrapper must be a GUI executable.

        pip generates GUI-subsystem wrappers for ``[project.gui-scripts]``
        entries.  This ensures that the script does **not** flash a console
        window, which is the correct behaviour for graphical applications.
        """
        wrapper = venv_with_packages / _SCRIPTS_DIR / "lab-gui.exe"
        subsystem = inspect_pe(wrapper)
        assert subsystem == "GUI", (
            f"Expected GUI entrypoint to be GUI, got {subsystem}. "
            "project.gui-scripts wrappers should be GUI-subsystem executables."
        )

    @pytest.mark.skipif(not _IS_WINDOWS, reason="GUI entrypoint .exe only on Windows")
    def test_gui_entrypoint_runs(self, venv_with_packages: Path) -> None:
        """The GUI entrypoint should execute and exit cleanly."""
        wrapper = venv_with_packages / _SCRIPTS_DIR / "lab-gui.exe"
        scenario = _make_venv_scenario(
            "venv-gui-entrypoint",
            str(wrapper),
            [],
            fixture="pkg_gui",
            description="venv GUI entrypoint (project.gui-scripts)",
        )
        result = run_scenario(scenario, timeout=15)
        assert result.exit_code == 0

    @pytest.mark.skipif(not _IS_WINDOWS, reason="GUI entrypoint .exe only on Windows")
    def test_gui_entrypoint_no_console_window(self, venv_with_packages: Path) -> None:
        """GUI entry-point wrappers should NOT create a console window.

        Expectations source: ``EXPECTATIONS["venv-gui-entrypoint"]``

        The GUI wrapper is a GUI-subsystem PE, and its child pythonw.exe
        should also be GUI-subsystem.  If the venv tooling creates a CUI
        trampoline for pythonw.exe, a console window will flash — this is
        a known deviation documented in ``KNOWN_DEVIATIONS``.
        """
        wrapper = venv_with_packages / _SCRIPTS_DIR / "lab-gui.exe"
        scenario = _make_venv_scenario(
            "venv-gui-ep-no-console",
            str(wrapper),
            [],
            fixture="pkg_gui",
        )
        result = run_scenario(scenario, timeout=15)

        expected = EXPECTATIONS["venv-gui-entrypoint"]
        if result.console_window_detected is not None:
            deviation = is_known_deviation("venv-gui-entrypoint", "console_window")
            if result.console_window_detected != expected.console_window and deviation is not None:
                pytest.xfail(
                    f"Known deviation: console_window={result.console_window_detected}, "
                    f"ideal={expected.console_window}.  {deviation.reason}"
                )
            assert result.console_window_detected == expected.console_window, (
                f"GUI entrypoint console_window: expected {expected.console_window}, "
                f"got {result.console_window_detected}"
            )

    @pytest.mark.skipif(not _IS_WINDOWS, reason="PE inspection only meaningful on Windows")
    def test_gui_entrypoint_file_info(self, venv_with_packages: Path) -> None:
        """Document the GUI entrypoint wrapper size and PE details."""
        wrapper = venv_with_packages / _SCRIPTS_DIR / "lab-gui.exe"
        size = wrapper.stat().st_size
        pe = inspect_pe(wrapper)
        print(f"\n  lab-gui wrapper: {wrapper} ({size:,} bytes, PE={pe})")
        assert size > 0

    def test_gui_entrypoint_non_windows(self, venv_with_packages: Path) -> None:
        """On non-Windows, GUI entrypoints are plain scripts that run successfully."""
        if _IS_WINDOWS:
            pytest.skip("Only meaningful on non-Windows")
        # On Linux/macOS pip installs gui-scripts as plain scripts (no .exe),
        # functionally equivalent to console scripts.
        wrapper = venv_with_packages / _SCRIPTS_DIR / "lab-gui"
        assert wrapper.is_file(), (
            f"GUI entrypoint script not found: {wrapper}. "
            "On non-Windows pip should still create a script for gui-scripts."
        )
        # Execute the script and verify it exits cleanly.
        scenario = _make_venv_scenario(
            "venv-gui-entrypoint-nix",
            str(wrapper),
            [],
            fixture="pkg_gui",
            description="venv GUI entrypoint on non-Windows",
        )
        result = run_scenario(scenario, timeout=15)
        assert result.exit_code == 0


# ===================================================================
# 5. Dual package (project.scripts + project.gui-scripts) in venv
# ===================================================================


class TestVenvDualEntrypoints:
    """Tests for packages that expose both console and GUI entrypoints.

    The ``pkg_dual`` fixture defines:
    - ``[project.scripts]``:     ``lab-dual-console``
    - ``[project.gui-scripts]``: ``lab-dual-gui``

    On Windows each entrypoint should receive the correct PE subsystem.
    """

    def test_dual_console_entrypoint_exists(self, venv_with_packages: Path) -> None:
        """The dual-package console entrypoint should exist."""
        wrapper = venv_with_packages / _SCRIPTS_DIR / f"lab-dual-console{_EXE_SUFFIX}"
        assert wrapper.is_file(), f"Dual console entrypoint not found: {wrapper}"

    def test_dual_console_entrypoint_runs(self, venv_with_packages: Path) -> None:
        """The dual-package console entrypoint should produce stdout."""
        wrapper = venv_with_packages / _SCRIPTS_DIR / f"lab-dual-console{_EXE_SUFFIX}"
        scenario = _make_venv_scenario(
            "venv-dual-console-entrypoint",
            str(wrapper),
            [],
            fixture="pkg_dual",
            description="venv dual-package console entrypoint",
        )
        result = run_scenario(scenario, timeout=15)
        assert result.exit_code == 0
        assert result.stdout_available is True
        assert result.stdout_text is not None
        assert "hello from lab-dual-console" in result.stdout_text

    @pytest.mark.skipif(not _IS_WINDOWS, reason="PE inspection only meaningful on Windows")
    def test_dual_console_entrypoint_is_cui(self, venv_with_packages: Path) -> None:
        """The console entrypoint from a dual package must be CUI on Windows."""
        wrapper = venv_with_packages / _SCRIPTS_DIR / "lab-dual-console.exe"
        subsystem = inspect_pe(wrapper)
        assert subsystem == "CUI", f"Expected dual console entrypoint to be CUI, got {subsystem}"

    @pytest.mark.skipif(not _IS_WINDOWS, reason="GUI entrypoint .exe only on Windows")
    def test_dual_gui_entrypoint_exists(self, venv_with_packages: Path) -> None:
        """The dual-package GUI entrypoint should exist on Windows."""
        wrapper = venv_with_packages / _SCRIPTS_DIR / "lab-dual-gui.exe"
        assert wrapper.is_file(), f"Dual GUI entrypoint not found: {wrapper}"

    @pytest.mark.skipif(not _IS_WINDOWS, reason="GUI entrypoint .exe only on Windows")
    def test_dual_gui_entrypoint_is_gui(self, venv_with_packages: Path) -> None:
        """The GUI entrypoint from a dual package must be GUI on Windows."""
        wrapper = venv_with_packages / _SCRIPTS_DIR / "lab-dual-gui.exe"
        subsystem = inspect_pe(wrapper)
        assert subsystem == "GUI", f"Expected dual GUI entrypoint to be GUI, got {subsystem}"

    @pytest.mark.skipif(not _IS_WINDOWS, reason="GUI entrypoint .exe only on Windows")
    def test_dual_gui_entrypoint_runs(self, venv_with_packages: Path) -> None:
        """The dual-package GUI entrypoint should exit cleanly."""
        wrapper = venv_with_packages / _SCRIPTS_DIR / "lab-dual-gui.exe"
        scenario = _make_venv_scenario(
            "venv-dual-gui-entrypoint",
            str(wrapper),
            [],
            fixture="pkg_dual",
            description="venv dual-package GUI entrypoint",
        )
        result = run_scenario(scenario, timeout=15)
        assert result.exit_code == 0

    @pytest.mark.skipif(not _IS_WINDOWS, reason="PE inspection only meaningful on Windows")
    def test_dual_entrypoints_file_info(self, venv_with_packages: Path) -> None:
        """Document sizes and PE subsystems of both dual entrypoints."""
        console_wrapper = venv_with_packages / _SCRIPTS_DIR / "lab-dual-console.exe"
        gui_wrapper = venv_with_packages / _SCRIPTS_DIR / "lab-dual-gui.exe"
        c_size = console_wrapper.stat().st_size
        g_size = gui_wrapper.stat().st_size
        c_pe = inspect_pe(console_wrapper)
        g_pe = inspect_pe(gui_wrapper)
        print(f"\n  lab-dual-console: {c_size:,} bytes, PE={c_pe}")
        print(f"  lab-dual-gui:     {g_size:,} bytes, PE={g_pe}")
        assert c_pe == "CUI"
        assert g_pe == "GUI"

    @pytest.mark.skipif(not _IS_WINDOWS, reason="Console detection only meaningful on Windows")
    def test_dual_console_has_console_window(self, venv_with_packages: Path) -> None:
        """The dual-package console entrypoint (CUI) should create a console."""
        wrapper = venv_with_packages / _SCRIPTS_DIR / "lab-dual-console.exe"
        scenario = _make_venv_scenario(
            "venv-dual-console-window",
            str(wrapper),
            [],
            fixture="pkg_dual",
        )
        result = run_scenario(scenario, timeout=15)
        # Only assert when the process tree was observable.
        if result.console_window_detected is not None and result.processes:
            assert result.console_window_detected is True

    @pytest.mark.skipif(not _IS_WINDOWS, reason="Console detection only meaningful on Windows")
    def test_dual_gui_no_console_window(self, venv_with_packages: Path) -> None:
        """The dual-package GUI entry-point should NOT create a console window.

        Expectations source: ``EXPECTATIONS["venv-dual-gui-entrypoint"]``

        If the venv tooling creates a CUI trampoline for pythonw.exe, a
        console window will flash — this is a known deviation documented
        in ``KNOWN_DEVIATIONS``.
        """
        wrapper = venv_with_packages / _SCRIPTS_DIR / "lab-dual-gui.exe"
        scenario = _make_venv_scenario(
            "venv-dual-gui-no-console",
            str(wrapper),
            [],
            fixture="pkg_dual",
        )
        result = run_scenario(scenario, timeout=15)

        expected = EXPECTATIONS["venv-dual-gui-entrypoint"]
        if result.console_window_detected is not None:
            deviation = is_known_deviation("venv-dual-gui-entrypoint", "console_window")
            if result.console_window_detected != expected.console_window and deviation is not None:
                pytest.xfail(
                    f"Known deviation: console_window={result.console_window_detected}, "
                    f"ideal={expected.console_window}.  {deviation.reason}"
                )
            assert result.console_window_detected == expected.console_window, (
                f"Dual GUI entrypoint console_window: expected {expected.console_window}, "
                f"got {result.console_window_detected}"
            )

    def test_dual_non_windows_both_run(self, venv_with_packages: Path) -> None:
        """On non-Windows, both entrypoints should exist and execute cleanly."""
        if _IS_WINDOWS:
            pytest.skip("Only meaningful on non-Windows")
        console_ep = venv_with_packages / _SCRIPTS_DIR / "lab-dual-console"
        gui_ep = venv_with_packages / _SCRIPTS_DIR / "lab-dual-gui"
        assert console_ep.is_file(), f"Dual console script not found: {console_ep}"
        assert gui_ep.is_file(), f"Dual GUI script not found: {gui_ep}"

        # Execute both entrypoints and verify they exit cleanly.
        for name, path in [("console", console_ep), ("gui", gui_ep)]:
            scenario = _make_venv_scenario(
                f"venv-dual-{name}-entrypoint-nix",
                str(path),
                [],
                fixture="pkg_dual",
                description=f"venv dual-package {name} entrypoint on non-Windows",
            )
            result = run_scenario(scenario, timeout=15)
            assert result.exit_code == 0, (
                f"Dual {name} entrypoint failed with exit code {result.exit_code}"
            )
