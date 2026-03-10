"""
Integration tests: uv run scenarios.

TODO(M3): Implement full uv run observation.
"""

import shutil

import pytest

from launch_lab.matrix import get_scenario
from launch_lab.runner import run_scenario


@pytest.fixture(autouse=True)
def require_uv():
    if shutil.which("uv") is None:
        pytest.skip("uv not on PATH")


def test_uv_run_script_py_result_has_correct_id():
    """uv run hello.py should produce a result with the correct scenario_id."""
    scenario = get_scenario("uv-run-script-py")
    assert scenario is not None
    result = run_scenario(scenario)
    assert result.scenario_id == "uv-run-script-py"
    # TODO(M3): Assert exit_code == 0, stdout available, etc.
