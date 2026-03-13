"""
Unit tests for the process runner (runner.py).

These tests validate runner logic and cross-platform graceful degradation.
They do not require Windows or any external tools.
"""

import json
import sys
from pathlib import Path

import pytest

from launch_lab.matrix import Scenario
from launch_lab.models import LauncherKind, ScenarioResult
from launch_lab.runner import _build_command, _parse_launcher, run_scenario


def _make_scenario(**kwargs) -> Scenario:
    defaults = dict(
        scenario_id="test-runner",
        launcher="python",
        mode="script.py",
        fixture="raw_py",
        args=["fixtures/raw_py/hello.py"],
        description="unit test scenario",
    )
    defaults.update(kwargs)
    return Scenario(**defaults)


class TestBuildCommand:
    """Tests for _build_command helper."""

    def test_simple_command(self):
        s = _make_scenario(launcher="python", args=["hello.py"])
        assert _build_command(s) == ["python", "hello.py"]

    def test_multi_arg_command(self):
        s = _make_scenario(launcher="uv", args=["run", "hello.py"])
        result = _build_command(s)
        # The first element may be a full path when custom uv is configured
        assert Path(result[0]).stem == "uv"
        assert result[1:] == ["run", "hello.py"]

    def test_empty_args(self):
        s = _make_scenario(launcher="python", args=[])
        assert _build_command(s) == ["python"]


class TestParseLauncher:
    """Tests for _parse_launcher helper."""

    def test_known_launchers(self):
        assert _parse_launcher("python") == LauncherKind.PYTHON
        assert _parse_launcher("pythonw") == LauncherKind.PYTHONW
        assert _parse_launcher("uv") == LauncherKind.UV

    def test_unknown_launcher(self):
        assert _parse_launcher("some-unknown-tool") == LauncherKind.UNKNOWN


class TestRunScenario:
    """Tests for run_scenario — executes real processes cross-platform."""

    def test_run_python_script(self):
        """Running a simple Python script should work cross-platform."""
        s = _make_scenario()
        result = run_scenario(s, timeout=15)
        assert result.scenario_id == "test-runner"
        assert result.platform == sys.platform
        assert result.exit_code == 0
        assert result.stdout_available is True
        assert result.stdout_text is not None
        assert "hello from raw_py/hello.py" in result.stdout_text

    def test_run_nonexistent_launcher(self):
        """A scenario with a non-existent launcher should handle gracefully."""
        s = _make_scenario(launcher="nonexistent-launcher-xyz-12345", args=[])
        result = run_scenario(s, timeout=5)
        assert result.exit_code is None
        assert result.stdout_available is False
        assert result.stderr_text is not None
        # runner.py sets this message format for FileNotFoundError
        assert "Executable not found" in result.stderr_text

    def test_result_has_all_fields(self):
        """The result should contain all ScenarioResult fields."""
        s = _make_scenario()
        result = run_scenario(s, timeout=15)
        assert isinstance(result, ScenarioResult)
        # Check identity fields
        assert result.python_version
        assert result.launcher == LauncherKind.PYTHON
        assert result.mode == "script.py"
        assert result.fixture == "raw_py"

    def test_result_serialises_to_json(self):
        """The result should serialise cleanly to JSON."""
        s = _make_scenario()
        result = run_scenario(s, timeout=15)
        serialised = result.model_dump_json()
        data = json.loads(serialised)
        assert data["scenario_id"] == "test-runner"
        assert "stdout_available" in data
        assert "stderr_available" in data
        assert "visible_window_detected" in data
        assert "console_window_detected" in data

    def test_save_artifact(self, tmp_path):
        """Running with save_artifact should produce a JSON file."""
        s = _make_scenario()
        result = run_scenario(s, timeout=15, save_artifact=True, artifact_dir=tmp_path)
        artifact = tmp_path / f"{result.scenario_id}.json"
        assert artifact.exists()
        data = json.loads(artifact.read_text())
        assert data["scenario_id"] == "test-runner"
        assert data["exit_code"] == 0

    def test_windows_fields_none_on_non_windows(self):
        """On non-Windows, window-detection fields should be None."""
        if sys.platform == "win32":
            pytest.skip("Test only meaningful on non-Windows")
        s = _make_scenario()
        result = run_scenario(s, timeout=15)
        assert result.visible_window_detected is None
        assert result.console_window_detected is None
        assert result.creation_flags is None
        assert result.processes == []
