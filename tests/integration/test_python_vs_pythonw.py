"""
Integration tests: direct python vs pythonw launch.

These tests spawn real processes and verify observable behaviour.
They are skipped on non-Windows unless the scenario does not require Windows.

Covered scenarios:
  - python-script-py   : python  hello.py   → CUI, console expected, stdout produced
  - python-script-pyw  : python  hello.pyw  → CUI, may delegate to pythonw
  - pythonw-script-py  : pythonw hello.py   → GUI, no console window, no stdout produced
  - pythonw-script-pyw : pythonw hello.pyw  → GUI, no console window, no stdout produced
"""

import json
import sys
from pathlib import Path

import pytest

from launch_lab.matrix import get_scenario
from launch_lab.runner import run_scenario

# ---------------------------------------------------------------------------
# python  hello.py  — console subsystem, stdout is available
# ---------------------------------------------------------------------------


@pytest.mark.skipif(sys.platform != "win32", reason="Windows-only integration test")
def test_python_script_py_exits_zero():
    """python hello.py should exit 0 with available stdout."""
    scenario = get_scenario("python-script-py")
    assert scenario is not None
    result = run_scenario(scenario)
    assert result.scenario_id == "python-script-py"
    assert result.exit_code == 0
    assert result.stdout_available is True


@pytest.mark.skipif(sys.platform != "win32", reason="Windows-only integration test")
def test_python_script_py_pe_subsystem():
    """python.exe should be classified as a CUI executable."""
    scenario = get_scenario("python-script-py")
    assert scenario is not None
    result = run_scenario(scenario)
    assert result.pe_subsystem == "CUI"


@pytest.mark.skipif(sys.platform != "win32", reason="Windows-only integration test")
def test_python_script_py_stdout_content():
    """python hello.py should produce recognisable stdout output."""
    scenario = get_scenario("python-script-py")
    assert scenario is not None
    result = run_scenario(scenario)
    assert result.stdout_text is not None
    assert "hello from raw_py/hello.py" in result.stdout_text


@pytest.mark.skipif(sys.platform != "win32", reason="Windows-only integration test")
def test_python_script_py_resolved_executable():
    """The resolved executable should point to an actual path."""
    scenario = get_scenario("python-script-py")
    assert scenario is not None
    result = run_scenario(scenario)
    assert result.resolved_executable is not None
    assert Path(result.resolved_executable).exists()


# ---------------------------------------------------------------------------
# python  hello.pyw  — Windows-only; py launcher may invoke pythonw
# ---------------------------------------------------------------------------


@pytest.mark.skipif(sys.platform != "win32", reason="Windows-only integration test")
def test_python_script_pyw_exits_zero():
    """python hello.pyw should exit 0."""
    scenario = get_scenario("python-script-pyw")
    assert scenario is not None
    result = run_scenario(scenario)
    assert result.scenario_id == "python-script-pyw"
    assert result.exit_code == 0


# ---------------------------------------------------------------------------
# pythonw  hello.py  — GUI subsystem, no console window expected
# ---------------------------------------------------------------------------


@pytest.mark.skipif(sys.platform != "win32", reason="Windows-only integration test")
def test_pythonw_script_py_exits_zero():
    """pythonw hello.py should exit 0."""
    scenario = get_scenario("pythonw-script-py")
    assert scenario is not None
    result = run_scenario(scenario)
    assert result.scenario_id == "pythonw-script-py"
    assert result.exit_code == 0


@pytest.mark.skipif(sys.platform != "win32", reason="Windows-only integration test")
def test_pythonw_script_py_pe_subsystem():
    """pythonw.exe should be classified as a GUI executable."""
    scenario = get_scenario("pythonw-script-py")
    assert scenario is not None
    result = run_scenario(scenario)
    assert result.pe_subsystem == "GUI"


@pytest.mark.skipif(sys.platform != "win32", reason="Windows-only integration test")
def test_pythonw_script_py_no_console_window():
    """pythonw should NOT produce a console window."""
    scenario = get_scenario("pythonw-script-py")
    assert scenario is not None
    result = run_scenario(scenario)
    # pythonw is a GUI-subsystem exe; it should not create a console window.
    # visible_window_detected and console_window_detected should be False
    # (or None if detection could not run).
    if result.console_window_detected is not None:
        assert result.console_window_detected is False


# ---------------------------------------------------------------------------
# pythonw  hello.pyw  — GUI subsystem, no console window expected
# ---------------------------------------------------------------------------


@pytest.mark.skipif(sys.platform != "win32", reason="Windows-only integration test")
def test_pythonw_script_pyw_exits_zero():
    """pythonw hello.pyw should exit 0."""
    scenario = get_scenario("pythonw-script-pyw")
    assert scenario is not None
    result = run_scenario(scenario)
    assert result.scenario_id == "pythonw-script-pyw"
    assert result.exit_code == 0


@pytest.mark.skipif(sys.platform != "win32", reason="Windows-only integration test")
def test_pythonw_script_pyw_pe_subsystem():
    """pythonw.exe should be classified as a GUI executable."""
    scenario = get_scenario("pythonw-script-pyw")
    assert scenario is not None
    result = run_scenario(scenario)
    assert result.pe_subsystem == "GUI"


# ---------------------------------------------------------------------------
# Evidence artifact capture
# ---------------------------------------------------------------------------


@pytest.mark.skipif(sys.platform != "win32", reason="Windows-only integration test")
def test_python_script_py_artifact_saved(tmp_path):
    """Running with save_artifact should write a JSON file."""
    scenario = get_scenario("python-script-py")
    assert scenario is not None
    result = run_scenario(scenario, save_artifact=True, artifact_dir=tmp_path)
    artifact = tmp_path / f"{result.scenario_id}.json"
    assert artifact.exists()
    data = json.loads(artifact.read_text())
    assert data["scenario_id"] == "python-script-py"
    assert data["exit_code"] == 0
    assert "stdout_available" in data
    assert "stderr_available" in data
    assert "visible_window_detected" in data


@pytest.mark.skipif(sys.platform != "win32", reason="Windows-only integration test")
def test_pythonw_script_py_artifact_saved(tmp_path):
    """Running pythonw with save_artifact should write a JSON file."""
    scenario = get_scenario("pythonw-script-py")
    assert scenario is not None
    result = run_scenario(scenario, save_artifact=True, artifact_dir=tmp_path)
    artifact = tmp_path / f"{result.scenario_id}.json"
    assert artifact.exists()
    data = json.loads(artifact.read_text())
    assert data["scenario_id"] == "pythonw-script-py"
    assert data["pe_subsystem"] == "GUI"


# ---------------------------------------------------------------------------
# Cross-platform smoke tests (non-Windows)
# ---------------------------------------------------------------------------


@pytest.mark.skipif(sys.platform == "win32", reason="Non-Windows graceful-degradation test")
def test_runner_returns_none_for_windows_fields_on_non_windows():
    """On non-Windows, window-detection fields should be None."""
    scenario = get_scenario("python-script-py")
    assert scenario is not None
    result = run_scenario(scenario)
    assert result.visible_window_detected is None
    assert result.console_window_detected is None
    assert result.creation_flags is None
    assert result.processes == []
