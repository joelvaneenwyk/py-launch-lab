"""
Integration tests: uvx and uv tool run scenarios.

Covered scenarios:
  - uvx-pkg-console          : uvx --from pkg_console lab-console → exit 0, stdout
  - uv-tool-run-pkg-console  : uv tool run --from pkg_console lab-console → exit 0, stdout
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
# uvx --from pkg_console lab-console — console tool via uvx
# ---------------------------------------------------------------------------


def test_uvx_pkg_console_exits_zero():
    """uvx --from pkg_console lab-console should exit 0."""
    scenario = get_scenario("uvx-pkg-console")
    assert scenario is not None
    result = run_scenario(scenario)
    assert result.scenario_id == "uvx-pkg-console"
    assert result.exit_code == 0


def test_uvx_pkg_console_stdout_content():
    """uvx --from pkg_console lab-console should produce recognisable stdout."""
    scenario = get_scenario("uvx-pkg-console")
    assert scenario is not None
    result = run_scenario(scenario)
    assert result.stdout_available is True
    assert result.stdout_text is not None
    assert "hello from lab-console" in result.stdout_text


def test_uvx_pkg_console_resolved_executable():
    """The resolved executable for uvx should point to an actual path."""
    scenario = get_scenario("uvx-pkg-console")
    assert scenario is not None
    result = run_scenario(scenario)
    assert result.resolved_executable is not None
    assert Path(result.resolved_executable).exists()


def test_uvx_pkg_console_artifact_saved(tmp_path):
    """Running with save_artifact should write a JSON file."""
    scenario = get_scenario("uvx-pkg-console")
    assert scenario is not None
    result = run_scenario(scenario, save_artifact=True, artifact_dir=tmp_path)
    artifact = tmp_path / f"{result.scenario_id}.json"
    assert artifact.exists()
    data = json.loads(artifact.read_text())
    assert data["scenario_id"] == "uvx-pkg-console"
    assert data["exit_code"] == 0
    assert "stdout_available" in data


# ---------------------------------------------------------------------------
# uv tool run --from pkg_console lab-console — equivalent to uvx
# ---------------------------------------------------------------------------


def test_uv_tool_run_pkg_console_exits_zero():
    """uv tool run --from pkg_console lab-console should exit 0."""
    scenario = get_scenario("uv-tool-run-pkg-console")
    assert scenario is not None
    result = run_scenario(scenario)
    assert result.scenario_id == "uv-tool-run-pkg-console"
    assert result.exit_code == 0


def test_uv_tool_run_pkg_console_stdout_content():
    """uv tool run should produce the same stdout as uvx."""
    scenario = get_scenario("uv-tool-run-pkg-console")
    assert scenario is not None
    result = run_scenario(scenario)
    assert result.stdout_available is True
    assert result.stdout_text is not None
    assert "hello from lab-console" in result.stdout_text


def test_uv_tool_run_pkg_console_artifact_saved(tmp_path):
    """Running with save_artifact should write a JSON file."""
    scenario = get_scenario("uv-tool-run-pkg-console")
    assert scenario is not None
    result = run_scenario(scenario, save_artifact=True, artifact_dir=tmp_path)
    artifact = tmp_path / f"{result.scenario_id}.json"
    assert artifact.exists()
    data = json.loads(artifact.read_text())
    assert data["scenario_id"] == "uv-tool-run-pkg-console"
    assert data["exit_code"] == 0


# ---------------------------------------------------------------------------
# Cross-platform smoke tests (non-Windows)
# ---------------------------------------------------------------------------


def test_uvx_windows_fields_none_on_non_windows():
    """On non-Windows, window-detection fields should be None."""
    if sys.platform == "win32":
        pytest.skip("Non-Windows graceful-degradation test")
    scenario = get_scenario("uvx-pkg-console")
    assert scenario is not None
    result = run_scenario(scenario)
    assert result.visible_window_detected is None
    assert result.console_window_detected is None
    assert result.creation_flags is None
    assert result.processes == []
