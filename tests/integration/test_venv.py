"""
Integration tests: venv python/pythonw executables and entrypoint scripts.

These tests create temporary virtual environments, install fixture packages
into them, and verify the observable behaviour of:

1. **venv python / pythonw executables**
   - On Windows the venv ``python.exe`` is a CUI (console-subsystem) copy or
     symlink of the base interpreter.  It should behave identically to the
     system ``python.exe``: allocate a console window and produce stdout.
   - The venv ``pythonw.exe`` is the GUI-subsystem counterpart.  It should
     **not** allocate a console window.

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

See also
--------
- ``docs/scenario-matrix.md`` — human-readable scenario table
- ``src/launch_lab/matrix.py`` — formal scenario definitions
"""

from __future__ import annotations

import subprocess
import sys
import venv
from pathlib import Path

import pytest

from launch_lab.inspect_pe import inspect_pe
from launch_lab.matrix import Scenario
from launch_lab.models import LauncherKind
from launch_lab.runner import run_scenario

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------

_PROJECT_ROOT = Path(__file__).resolve().parents[2]
_FIXTURES = _PROJECT_ROOT / "fixtures"

_IS_WINDOWS = sys.platform == "win32"

# On Windows the venv Scripts dir is ``Scripts/``; elsewhere ``bin/``.
_SCRIPTS_DIR = "Scripts" if _IS_WINDOWS else "bin"
_EXE_SUFFIX = ".exe" if _IS_WINDOWS else ""


# ---------------------------------------------------------------------------
# Fixtures (pytest)
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def venv_dir(tmp_path_factory: pytest.TempPathFactory) -> Path:
    """Create a fresh virtual environment shared by all tests in this module.

    The venv is created once and reused across test functions.  Fixture
    packages are installed inside individual tests as needed.
    """
    venv_path = tmp_path_factory.mktemp("venv")
    venv.create(venv_path, with_pip=True)
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

    Installs: pkg_console, pkg_gui, pkg_dual.
    """
    for pkg in ("pkg_console", "pkg_gui", "pkg_dual"):
        pkg_path = _FIXTURES / pkg
        subprocess.check_call(
            [str(venv_python), "-m", "pip", "install", "--quiet", str(pkg_path)],
            timeout=120,
        )
    return venv_dir


# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------


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
        # Console window detection is best-effort; we only assert when the
        # detector was able to return a definitive answer.
        if result.console_window_detected is not None:
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
    def test_venv_pythonw_is_gui(self, venv_dir: Path) -> None:
        """On Windows the venv pythonw.exe must be a GUI executable.

        The venv copies (or symlinks) the base interpreter's ``pythonw.exe``
        which is a GUI-subsystem PE binary.  Launching it does **not**
        allocate a console window.
        """
        pythonw = venv_dir / _SCRIPTS_DIR / "pythonw.exe"
        subsystem = inspect_pe(pythonw)
        assert subsystem == "GUI", (
            f"Expected venv pythonw to be GUI, got {subsystem}. "
            "The venv pythonw.exe should be a GUI-subsystem executable."
        )

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
    def test_venv_pythonw_no_console_window(self, venv_dir: Path) -> None:
        """pythonw (GUI subsystem) should NOT produce a console window."""
        pythonw = venv_dir / _SCRIPTS_DIR / "pythonw.exe"
        script = _FIXTURES / "raw_py" / "hello.py"
        scenario = _make_venv_scenario(
            "venv-pythonw-no-console",
            str(pythonw),
            [str(script)],
            description="venv pythonw hello.py — should have no console",
        )
        result = run_scenario(scenario, timeout=15)
        # pythonw is a GUI-subsystem exe; it should not create a console
        if result.console_window_detected is not None:
            assert result.console_window_detected is False, (
                "venv pythonw.exe (GUI) should NOT create a console window"
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
        if result.console_window_detected is not None:
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
        """The GUI entrypoint (GUI subsystem) should NOT create a console window."""
        wrapper = venv_with_packages / _SCRIPTS_DIR / "lab-gui.exe"
        scenario = _make_venv_scenario(
            "venv-gui-ep-no-console",
            str(wrapper),
            [],
            fixture="pkg_gui",
        )
        result = run_scenario(scenario, timeout=15)
        if result.console_window_detected is not None:
            assert result.console_window_detected is False, (
                "project.gui-scripts entrypoint (GUI) should NOT create a console window"
            )

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
        assert subsystem == "CUI", (
            f"Expected dual console entrypoint to be CUI, got {subsystem}"
        )

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
        assert subsystem == "GUI", (
            f"Expected dual GUI entrypoint to be GUI, got {subsystem}"
        )

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
        if result.console_window_detected is not None:
            assert result.console_window_detected is True

    @pytest.mark.skipif(not _IS_WINDOWS, reason="Console detection only meaningful on Windows")
    def test_dual_gui_no_console_window(self, venv_with_packages: Path) -> None:
        """The dual-package GUI entrypoint (GUI) should NOT create a console."""
        wrapper = venv_with_packages / _SCRIPTS_DIR / "lab-dual-gui.exe"
        scenario = _make_venv_scenario(
            "venv-dual-gui-no-console",
            str(wrapper),
            [],
            fixture="pkg_dual",
        )
        result = run_scenario(scenario, timeout=15)
        if result.console_window_detected is not None:
            assert result.console_window_detected is False

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
