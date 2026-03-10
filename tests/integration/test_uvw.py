"""
Integration tests: uvw scenarios (Windows-only).

Covered scenarios:
  - uvw-run-script-py : uvw run hello.py → exit 0, GUI subsystem, no console

uvw is the GUI-subsystem companion to uv on Windows, analogous to pythonw.
"""

import json
import shutil
import sys

import pytest

from launch_lab.matrix import get_scenario
from launch_lab.runner import run_scenario


@pytest.fixture(autouse=True)
def require_windows_and_uvw():
    if sys.platform != "win32":
        pytest.skip("uvw is Windows-only")
    if shutil.which("uvw") is None:
        pytest.skip("uvw not on PATH")


# ---------------------------------------------------------------------------
# uvw run hello.py — GUI subsystem variant of uv
# ---------------------------------------------------------------------------


def test_uvw_run_script_py_exits_zero():
    """uvw run hello.py should exit 0."""
    scenario = get_scenario("uvw-run-script-py")
    assert scenario is not None
    result = run_scenario(scenario)
    assert result.scenario_id == "uvw-run-script-py"
    assert result.exit_code == 0


def test_uvw_run_script_py_pe_subsystem():
    """uvw.exe should be classified as a GUI executable."""
    scenario = get_scenario("uvw-run-script-py")
    assert scenario is not None
    result = run_scenario(scenario)
    assert result.pe_subsystem == "GUI"


def test_uvw_run_script_py_no_console_window():
    """uvw should NOT produce a console window."""
    scenario = get_scenario("uvw-run-script-py")
    assert scenario is not None
    result = run_scenario(scenario)
    if result.console_window_detected is not None:
        assert result.console_window_detected is False


def test_uvw_run_script_py_resolved_executable():
    """The resolved executable should point to an actual path."""
    scenario = get_scenario("uvw-run-script-py")
    assert scenario is not None
    result = run_scenario(scenario)
    assert result.resolved_executable is not None


# ---------------------------------------------------------------------------
# Evidence artifact capture
# ---------------------------------------------------------------------------


def test_uvw_run_script_py_artifact_saved(tmp_path):
    """Running with save_artifact should write a JSON file."""
    scenario = get_scenario("uvw-run-script-py")
    assert scenario is not None
    result = run_scenario(scenario, save_artifact=True, artifact_dir=tmp_path)
    artifact = tmp_path / f"{result.scenario_id}.json"
    assert artifact.exists()
    data = json.loads(artifact.read_text())
    assert data["scenario_id"] == "uvw-run-script-py"
    assert "pe_subsystem" in data
    assert "console_window_detected" in data
