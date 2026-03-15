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
from launch_lab.runner import (
    _MTIME_SENTINEL,
    _build_command,
    _parse_launcher,
    _read_stored_mtime,
    _uv_binary_mtime,
    _write_mtime_sentinel,
    run_scenario,
)


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
        from launch_lab.collect import artifact_filename

        s = _make_scenario()
        result = run_scenario(s, timeout=15, save_artifact=True, artifact_dir=tmp_path)
        artifact = tmp_path / artifact_filename(result)
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


class TestVenvMtimeHelpers:
    """Unit tests for the mtime-sentinel helpers used to track custom uv rebuilds."""

    def test_write_and_read_mtime(self, tmp_path):
        """Write a sentinel then read it back."""
        mtime = 1700000000.123
        _write_mtime_sentinel(tmp_path, mtime)
        assert (tmp_path / _MTIME_SENTINEL).exists()
        assert _read_stored_mtime(tmp_path) == pytest.approx(mtime)

    def test_read_missing_sentinel_returns_none(self, tmp_path):
        """Reading from a directory with no sentinel returns None."""
        assert _read_stored_mtime(tmp_path) is None

    def test_read_malformed_sentinel_returns_none(self, tmp_path):
        """A sentinel file with non-numeric content returns None."""
        (tmp_path / _MTIME_SENTINEL).write_text("not-a-number", encoding="utf-8")
        assert _read_stored_mtime(tmp_path) is None

    def test_uv_binary_mtime_real_file(self, tmp_path):
        """_uv_binary_mtime returns a float for an existing file."""
        fake_bin = tmp_path / "uv"
        fake_bin.write_text("binary", encoding="utf-8")
        mtime = _uv_binary_mtime(str(fake_bin))
        assert mtime is not None
        assert isinstance(mtime, float)

    def test_uv_binary_mtime_missing_returns_none(self, tmp_path):
        """_uv_binary_mtime returns None for a missing path."""
        assert _uv_binary_mtime(str(tmp_path / "nonexistent")) is None

    def test_mtime_roundtrip_detects_rebuild(self, tmp_path):
        """After writing a sentinel, changing the mtime should be detectable."""
        import time

        fake_bin = tmp_path / "uv"
        fake_bin.write_text("v1", encoding="utf-8")
        mtime_v1 = _uv_binary_mtime(str(fake_bin))
        assert mtime_v1 is not None

        venv_dir = tmp_path / "venv"
        venv_dir.mkdir()
        _write_mtime_sentinel(venv_dir, mtime_v1)

        # Simulate a rebuild: wait for filesystem clock tick then touch the file
        time.sleep(0.05)
        fake_bin.write_text("v2", encoding="utf-8")
        mtime_v2 = _uv_binary_mtime(str(fake_bin))
        stored = _read_stored_mtime(venv_dir)

        # Either the mtime changed (most systems) or the test machine is
        # very fast — either way the comparison logic works.
        assert stored == pytest.approx(mtime_v1)
        # If the FS has sub-second precision the mtimes will differ.
        if mtime_v2 != mtime_v1:
            assert mtime_v2 != stored  # would trigger venv rebuild
