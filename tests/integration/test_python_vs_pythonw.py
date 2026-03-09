"""
Integration tests: direct python vs pythonw launch.

These tests spawn real processes and verify observable behaviour.
They are skipped on non-Windows unless the scenario does not require Windows.

TODO(M2): Implement full observation (window detection, PE inspection).
"""

import sys

import pytest

from launch_lab.matrix import get_scenario
from launch_lab.runner import run_scenario


@pytest.mark.skipif(sys.platform != "win32", reason="Windows-only integration test")
def test_python_script_py_exits_zero():
    """python hello.py should exit 0."""
    scenario = get_scenario("python-script-py")
    assert scenario is not None
    result = run_scenario(scenario)
    # TODO(M2): Assert console_window_detected, pe_subsystem, etc.
    assert result.scenario_id == "python-script-py"


@pytest.mark.skipif(sys.platform != "win32", reason="Windows-only integration test")
def test_pythonw_script_py_exits_zero():
    """pythonw hello.py should exit 0."""
    scenario = get_scenario("pythonw-script-py")
    assert scenario is not None
    result = run_scenario(scenario)
    assert result.scenario_id == "pythonw-script-py"
