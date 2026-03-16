"""
Integration tests: uv tool install scenarios.

Covered scenarios:
  - uv-tool-install-console : uv tool install pkg_console → exit 0
  - uv-tool-install-gui     : uv tool install pkg_gui     → exit 0 (Windows-only)

Each test installs a fixture package via ``uv tool install`` and verifies the
installation succeeds.  A session-scoped fixture uninstalls the packages after
all tests in this module complete.
"""

import json
import shutil
import subprocess
import sys

import pytest

from launch_lab.matrix import get_scenario
from launch_lab.runner import run_scenario


@pytest.fixture(autouse=True)
def require_uv():
    if shutil.which("uv") is None:
        pytest.skip("uv not on PATH")


@pytest.fixture(autouse=True, scope="module")
def _cleanup_tool_installs():
    """Uninstall fixture packages after all tests in this module."""
    yield
    for pkg in ("lab-console", "lab-window-gui"):
        try:
            subprocess.run(
                ["uv", "tool", "uninstall", pkg],
                capture_output=True,
                timeout=30,
            )
        except (FileNotFoundError, subprocess.TimeoutExpired):
            pass


# ---------------------------------------------------------------------------
# uv tool install pkg_console — console entrypoint
# ---------------------------------------------------------------------------


def test_uv_tool_install_console_exits_zero():
    """uv tool install pkg_console should exit 0."""
    scenario = get_scenario("uv-tool-install-console")
    assert scenario is not None
    result = run_scenario(scenario)
    assert result.scenario_id == "uv-tool-install-console"
    assert result.exit_code == 0


def test_uv_tool_install_console_resolved_executable():
    """The resolved executable should point to uv."""
    scenario = get_scenario("uv-tool-install-console")
    assert scenario is not None
    result = run_scenario(scenario)
    assert result.resolved_executable is not None


def test_uv_tool_install_console_artifact_saved(tmp_path):
    """Running with save_artifact should write a JSON file."""
    scenario = get_scenario("uv-tool-install-console")
    assert scenario is not None
    result = run_scenario(scenario, save_artifact=True, artifact_dir=tmp_path)
    artifact = tmp_path / f"{result.scenario_id}.json"
    assert artifact.exists()
    data = json.loads(artifact.read_text())
    assert data["scenario_id"] == "uv-tool-install-console"
    assert "exit_code" in data
    assert "stdout_available" in data


# ---------------------------------------------------------------------------
# uv tool install pkg_gui — GUI entrypoint (Windows-only)
# ---------------------------------------------------------------------------


@pytest.mark.skipif(sys.platform != "win32", reason="GUI entrypoint is Windows-only")
def test_uv_tool_install_gui_exits_zero():
    """uv tool install pkg_gui should exit 0."""
    scenario = get_scenario("uv-tool-install-gui")
    assert scenario is not None
    result = run_scenario(scenario)
    assert result.scenario_id == "uv-tool-install-gui"
    assert result.exit_code == 0


@pytest.mark.skipif(sys.platform != "win32", reason="GUI entrypoint is Windows-only")
def test_uv_tool_install_gui_artifact_saved(tmp_path):
    """Running with save_artifact should write a JSON file."""
    scenario = get_scenario("uv-tool-install-gui")
    assert scenario is not None
    result = run_scenario(scenario, save_artifact=True, artifact_dir=tmp_path)
    artifact = tmp_path / f"{result.scenario_id}.json"
    assert artifact.exists()
    data = json.loads(artifact.read_text())
    assert data["scenario_id"] == "uv-tool-install-gui"
    assert "exit_code" in data
