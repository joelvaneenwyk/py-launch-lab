# Scenario Matrix

The full set of scenarios is defined in `src/launch_lab/matrix.py`.

This document provides a human-readable summary.

## Legend

| Column | Meaning |
|--------|---------|
| Scenario ID | Unique string key used in artifact filenames |
| Launcher | Top-level executable |
| Mode | Script or tool invocation style |
| Fixture | Input package or script |
| Win-only | Scenario is skipped on non-Windows |
| Needs uv | Requires uv on PATH |

## Direct Python / PythonW

| Scenario ID | Launcher | Mode | Fixture | Win-only | Needs uv |
|-------------|----------|------|---------|----------|----------|
| `python-script-py` | `python` | `script.py` | `raw_py` | No | No |
| `python-script-pyw` | `python` | `script.pyw` | `raw_pyw` | Yes | No |
| `pythonw-script-py` | `pythonw` | `script.py` | `raw_py` | Yes | No |
| `pythonw-script-pyw` | `pythonw` | `script.pyw` | `raw_pyw` | Yes | No |

## uv run

| Scenario ID | Launcher | Mode | Fixture | Win-only | Needs uv |
|-------------|----------|------|---------|----------|----------|
| `uv-run-script-py` | `uv` | `run script.py` | `raw_py` | No | Yes |
| `uv-run-script-pyw` | `uv` | `run script.pyw` | `raw_pyw` | No | Yes |
| `uv-run-gui-script` | `uv` | `run --gui-script script.py` | `raw_py` | Yes | Yes |
| `uvw-run-script-py` | `uvw` | `run script.py` | `raw_py` | Yes | Yes |

## uvx / uv tool run

| Scenario ID | Launcher | Mode | Fixture | Win-only | Needs uv |
|-------------|----------|------|---------|----------|----------|
| `uvx-pkg-console` | `uvx` | `tool run console fixture` | `pkg_console` | No | Yes |
| `uv-tool-run-pkg-console` | `uv` | `tool run console fixture` | `pkg_console` | No | Yes |

## uv tool install

| Scenario ID | Launcher | Mode | Fixture | Win-only | Needs uv |
|-------------|----------|------|---------|----------|----------|
| `uv-tool-install-console` | `uv` | `tool install console fixture` | `pkg_console` | No | Yes |
| `uv-tool-install-gui` | `uv` | `tool install gui fixture` | `pkg_gui` | Yes | Yes |

## Rust Shim

| Scenario ID | Launcher | Mode | Fixture | Win-only | Needs uv |
|-------------|----------|------|---------|----------|----------|
| `shim-python-script-py` | `pyshim-win` | `--hide-console python script.py` | `raw_py` | Yes | No |
| `shim-uv-run-script-py` | `pyshim-win` | `--hide-console uv run script.py` | `raw_py` | Yes | Yes |
