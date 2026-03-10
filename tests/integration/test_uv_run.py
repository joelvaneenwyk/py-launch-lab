"""
Integration tests: uv run scenarios.

Covered scenarios:
  - uv-run-script-py    : uv run hello.py     → exit 0, stdout available
  - uv-run-script-pyw   : uv run hello.pyw    → exit 0
  - uv-run-gui-script   : uv run --gui-script → exit 0 (Windows-only)
"""

import json
import shutil
import sys
from pathlib import Path

import pytest

from launch_lab.matrix import get_scenario
from launch_lab.runner import run_scenario


@pytest.fixture(autouse=True)
def require_uv():
    if shutil.which("uv") is None:
        pytest.skip("uv not on PATH")


# ---------------------------------------------------------------------------
# uv run hello.py — console script, stdout expected
# ---------------------------------------------------------------------------


def test_uv_run_script_py_exits_zero():
    """uv run hello.py should exit 0 with available stdout."""
    scenario = get_scenario("uv-run-script-py")
    assert scenario is not None
    result = run_scenario(scenario)
    assert result.scenario_id == "uv-run-script-py"
    assert result.exit_code == 0
    assert result.stdout_available is True


def test_uv_run_script_py_stdout_content():
    """uv run hello.py should produce recognisable stdout output."""
    scenario = get_scenario("uv-run-script-py")
    assert scenario is not None
    result = run_scenario(scenario)
    assert result.stdout_text is not None
    assert "hello from raw_py/hello.py" in result.stdout_text


def test_uv_run_script_py_resolved_executable():
    """The resolved executable should point to an actual path."""
    scenario = get_scenario("uv-run-script-py")
    assert scenario is not None
    result = run_scenario(scenario)
    assert result.resolved_executable is not None
    assert Path(result.resolved_executable).exists()


def test_uv_run_script_py_pe_subsystem():
    """uv.exe should be classified as CUI on Windows."""
    if sys.platform != "win32":
        pytest.skip("PE subsystem only meaningful on Windows")
    scenario = get_scenario("uv-run-script-py")
    assert scenario is not None
    result = run_scenario(scenario)
    assert result.pe_subsystem == "CUI"


# ---------------------------------------------------------------------------
# uv run hello.pyw — .pyw script via uv
# ---------------------------------------------------------------------------


def test_uv_run_script_pyw_exits_zero():
    """uv run hello.pyw should exit 0."""
    scenario = get_scenario("uv-run-script-pyw")
    assert scenario is not None
    result = run_scenario(scenario)
    assert result.scenario_id == "uv-run-script-pyw"
    assert result.exit_code == 0


# ---------------------------------------------------------------------------
# uv run --gui-script — Windows-only GUI mode
# ---------------------------------------------------------------------------


@pytest.mark.skipif(sys.platform != "win32", reason="--gui-script is Windows-only")
def test_uv_run_gui_script_exits_zero():
    """uv run --gui-script hello.py should exit 0."""
    scenario = get_scenario("uv-run-gui-script")
    assert scenario is not None
    result = run_scenario(scenario)
    assert result.scenario_id == "uv-run-gui-script"
    assert result.exit_code == 0


# ---------------------------------------------------------------------------
# Evidence artifact capture
# ---------------------------------------------------------------------------


def test_uv_run_script_py_artifact_saved(tmp_path):
    """Running with save_artifact should write a JSON file."""
    scenario = get_scenario("uv-run-script-py")
    assert scenario is not None
    result = run_scenario(scenario, save_artifact=True, artifact_dir=tmp_path)
    artifact = tmp_path / f"{result.scenario_id}.json"
    assert artifact.exists()
    data = json.loads(artifact.read_text())
    assert data["scenario_id"] == "uv-run-script-py"
    assert data["exit_code"] == 0
    assert "stdout_available" in data
    assert "stderr_available" in data


# ---------------------------------------------------------------------------
# Cross-platform smoke tests (non-Windows)
# ---------------------------------------------------------------------------


def test_uv_run_script_py_windows_fields_none_on_non_windows():
    """On non-Windows, window-detection fields should be None."""
    if sys.platform == "win32":
        pytest.skip("Non-Windows graceful-degradation test")
    scenario = get_scenario("uv-run-script-py")
    assert scenario is not None
    result = run_scenario(scenario)
    assert result.visible_window_detected is None
    assert result.console_window_detected is None
    assert result.creation_flags is None
    assert result.processes == []
