"""
Integration tests: pyshim-win Rust shim scenarios.

These tests validate the pyshim-win binary:
  - Builds successfully with `cargo build`
  - CLI argument parsing works correctly
  - JSON output matches the expected schema
  - Executable resolution on PATH works
  - PE subsystem detection produces valid values
"""

import json
import subprocess
import sys
from pathlib import Path

import pytest

# Root of the repository.
REPO_ROOT = Path(__file__).resolve().parent.parent.parent
CRATE_DIR = REPO_ROOT / "crates" / "pyshim-win"


@pytest.fixture(autouse=True)
def require_windows_for_shim_launch():
    """Skip tests that actually launch via the GUI shim on non-Windows."""
    # Build/schema tests can run everywhere; individual tests mark themselves
    # as windows-only if they exercise the Windows CreateProcess path.


def _shim_binary() -> Path | None:
    """Return the path to the built shim binary, or None if not built."""
    if sys.platform == "win32":
        name = "pyshim-win.exe"
    else:
        name = "pyshim-win"
    debug = CRATE_DIR / "target" / "debug" / name
    release = CRATE_DIR / "target" / "release" / name
    if release.exists():
        return release
    if debug.exists():
        return debug
    return None


# ---------------------------------------------------------------------------
# Build / compile tests (cross-platform)
# ---------------------------------------------------------------------------


class TestShimBuild:
    """Verify the Rust shim compiles correctly."""

    def test_cargo_build(self):
        """The crate should compile without errors."""
        result = subprocess.run(
            ["cargo", "build"],
            cwd=CRATE_DIR,
            capture_output=True,
            text=True,
            timeout=120,
        )
        assert result.returncode == 0, (
            f"cargo build failed:\nstdout={result.stdout}\nstderr={result.stderr}"
        )

    def test_cargo_test(self):
        """The crate's own unit tests should pass."""
        result = subprocess.run(
            ["cargo", "test"],
            cwd=CRATE_DIR,
            capture_output=True,
            text=True,
            timeout=120,
        )
        assert result.returncode == 0, (
            f"cargo test failed:\nstdout={result.stdout}\nstderr={result.stderr}"
        )


# ---------------------------------------------------------------------------
# CLI / JSON schema tests
# ---------------------------------------------------------------------------


class TestShimCLI:
    """Verify CLI behaviour and JSON output structure."""

    @pytest.fixture(autouse=True)
    def require_binary(self):
        """Skip if the shim binary is not available."""
        binary = _shim_binary()
        if binary is None:
            pytest.skip("pyshim-win binary not built")
        self.binary = binary

    def _run_shim(self, *args: str, timeout: int = 30) -> subprocess.CompletedProcess[str]:
        """Run the shim binary and return the result."""
        return subprocess.run(
            [str(self.binary), *args],
            capture_output=True,
            text=True,
            timeout=timeout,
        )

    def test_help_flag(self):
        """--help should exit 0 and print usage information."""
        result = self._run_shim("--help")
        assert result.returncode == 0
        assert "pyshim-win" in result.stdout.lower() or "usage" in result.stdout.lower()

    def test_version_flag(self):
        """--version should exit 0 and print a version string."""
        result = self._run_shim("--version")
        assert result.returncode == 0
        assert "pyshim-win" in result.stdout.lower() or "0." in result.stdout

    def test_missing_command_exits_nonzero(self):
        """Invoking without a command should produce an error."""
        result = self._run_shim()
        assert result.returncode != 0

    def test_unresolved_command_json_output(self):
        """A nonexistent command should produce JSON with an error."""
        result = self._run_shim("--", "__nonexistent_xyz_test__")
        # exit_code 127 = command not found
        assert result.returncode == 127
        data = json.loads(result.stdout)
        assert data["exit_code"] == 127
        assert data["resolved_executable"] is None
        assert data["error"] is not None
        assert "hide_console" in data

    def test_echo_command_json_output(self):
        """Running a simple command should produce valid JSON output."""
        if sys.platform == "win32":
            cmd = ["--", "cmd", "/c", "echo", "hello"]
        else:
            cmd = ["--", "echo", "hello"]
        result = self._run_shim(*cmd)
        # stdout contains the child's output followed by JSON
        lines = result.stdout.strip().split("\n")
        # The JSON block is the last part of stdout (starts with '{')
        json_start = None
        for i, line in enumerate(lines):
            if line.strip().startswith("{"):
                json_start = i
                break
        assert json_start is not None, f"No JSON found in output: {result.stdout}"
        json_text = "\n".join(lines[json_start:])
        data = json.loads(json_text)
        assert data["exit_code"] == 0
        assert data["resolved_executable"] is not None
        assert data["error"] is None
        assert isinstance(data["hide_console"], bool)
        assert "detected_subsystem" in data

    def test_hide_console_flag_reflected_in_json(self):
        """The --hide-console flag should be reflected in the JSON output."""
        if sys.platform == "win32":
            cmd = ["--hide-console", "--", "cmd", "/c", "echo", "test"]
        else:
            cmd = ["--hide-console", "--", "echo", "test"]
        result = self._run_shim(*cmd)
        lines = result.stdout.strip().split("\n")
        json_start = None
        for i, line in enumerate(lines):
            if line.strip().startswith("{"):
                json_start = i
                break
        assert json_start is not None
        json_text = "\n".join(lines[json_start:])
        data = json.loads(json_text)
        assert data["hide_console"] is True

    def test_detected_subsystem_field_present(self):
        """The JSON output should include a detected_subsystem field."""
        if sys.platform == "win32":
            cmd = ["--", "cmd", "/c", "echo", "test"]
        else:
            cmd = ["--", "echo", "test"]
        result = self._run_shim(*cmd)
        lines = result.stdout.strip().split("\n")
        json_start = None
        for i, line in enumerate(lines):
            if line.strip().startswith("{"):
                json_start = i
                break
        assert json_start is not None
        json_text = "\n".join(lines[json_start:])
        data = json.loads(json_text)
        assert "detected_subsystem" in data
        # On Linux, executables are NotPe; on Windows they could be Gui or Cui
        valid_values = ["Gui", "Cui", "Unknown", "NotPe", None]
        assert data["detected_subsystem"] in valid_values

    def test_python_resolution(self):
        """The shim should resolve 'python3' (or 'python') on PATH."""
        python_cmd = "python" if sys.platform == "win32" else "python3"
        result = self._run_shim("--", python_cmd, "-c", "print('ok')")
        lines = result.stdout.strip().split("\n")
        json_start = None
        for i, line in enumerate(lines):
            if line.strip().startswith("{"):
                json_start = i
                break
        assert json_start is not None
        json_text = "\n".join(lines[json_start:])
        data = json.loads(json_text)
        assert data["exit_code"] == 0
        assert data["resolved_executable"] is not None
        resolved = data["resolved_executable"].lower()
        assert python_cmd in resolved or "python" in resolved


# ---------------------------------------------------------------------------
# Windows-specific shim tests
# ---------------------------------------------------------------------------


class TestShimWindows:
    """Tests that exercise Windows-specific shim behaviour."""

    @pytest.fixture(autouse=True)
    def require_windows(self):
        if sys.platform != "win32":
            pytest.skip("pyshim-win Windows tests require Windows")
        binary = _shim_binary()
        if binary is None:
            pytest.skip("pyshim-win binary not built")
        self.binary = binary

    def _run_shim(self, *args: str, timeout: int = 30) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [str(self.binary), *args],
            capture_output=True,
            text=True,
            timeout=timeout,
        )

    def test_python_subsystem_is_cui(self):
        """python.exe should be detected as CUI subsystem."""
        result = self._run_shim("--", "python", "-c", "print('ok')")
        lines = result.stdout.strip().split("\n")
        json_start = next(
            (i for i, line in enumerate(lines) if line.strip().startswith("{")), None
        )
        assert json_start is not None
        data = json.loads("\n".join(lines[json_start:]))
        assert data["detected_subsystem"] == "Cui"

    def test_hide_console_prefers_pythonw(self):
        """With --hide-console, python should resolve to pythonw."""
        result = self._run_shim(
            "--hide-console", "--", "python", "-c", "import sys; print(sys.executable)"
        )
        lines = result.stdout.strip().split("\n")
        json_start = next(
            (i for i, line in enumerate(lines) if line.strip().startswith("{")),
            None,
        )
        assert json_start is not None
        data = json.loads("\n".join(lines[json_start:]))
        resolved = data.get("resolved_executable", "").lower()
        assert "pythonw" in resolved
