# Python Launch Lab — Project Plan

## Overview

This lab systematically measures how Python launch modes behave on Windows across every major launcher and packaging mechanism. Each scenario is run, inspected, and recorded as machine-readable evidence.

---

## Milestone M0 — Repo Skeleton ✅

- [x] Repository structure created
- [x] `pyproject.toml` with `launch_lab` package and `py-launch-lab` CLI
- [x] Python modules: `cli`, `models`, `matrix`, `runner`, `inspect_pe`, `detect_windows`, `collect`, `report`, `html_report`, `util`
- [x] Fixture directories: `pkg_console`, `pkg_gui`, `pkg_dual`, `raw_py`, `raw_pyw`, `direct_exec`
- [x] Rust crate `pyshim-win` compiling on Windows
- [x] GitHub Actions CI (`windows.yml`, `docs.yml`)
- [x] Basic unit tests: schema, matrix generation, importability

---

## Milestone M1 — Static PE Inspection ✅

- [x] Implement `inspect_pe.py`: read PE header from any Windows EXE
- [x] Classify `IMAGE_SUBSYSTEM_WINDOWS_GUI` vs `IMAGE_SUBSYSTEM_WINDOWS_CUI`
- [x] Support inspection of Python, PythonW, uv, uvw executables
- [x] Store `pe_subsystem` field in result objects
- [x] Unit tests for PE inspection (synthetic PE files and real executables on Windows)

---

## Milestone M2 — Direct Python vs PythonW Launch Validation ✅

- [x] Implement `runner.py`: spawn child processes with controlled environment
- [x] Detect whether spawned process opens a console window (`detect_windows.py` uses `CreateToolhelp32Snapshot`)
- [x] Detect `conhost.exe` appearing in process tree
- [x] Record `stdout_available`, `stderr_available`, `visible_window_detected`
- [x] Implement integration tests: `test_python_vs_pythonw.py`
- [x] Capture evidence artifacts for `python script.py` vs `pythonw script.py`

---

## Milestone M3 — uv and uvw Scenario Coverage ✅

- [x] Run scenarios for `uv run script.py`, `uv run script.pyw`, `uv run --gui-script`
- [x] Run scenarios for `uvx` and `uv tool run`
- [x] Run `uv tool install` for console and GUI fixture packages
- [x] Integration tests: `test_uv_run.py`, `test_uv_tool_install.py`, `test_uvx.py`, `test_uvw.py`
- [x] Populate `artifacts/json/` with per-scenario result JSON

---

## Milestone M4 — Rust Shim Integration ✅

- [x] Implement `pyshim-win` CLI with `--hide-console` flag (clap-based)
- [x] Implement `launch.rs`: spawn child process using `CreateProcessW` with `CREATE_NO_WINDOW` flag
- [x] Implement `resolve.rs`: locate `python`, `pythonw`, `uv`, `uvw` on PATH with GUI alternative support
- [x] Implement `detect.rs`: detect console vs GUI subsystem via PE header parsing
- [x] Emit structured JSON result from shim
- [x] Integration test: `test_shim.py`

---

## Milestone M5 — CI Artifacts and Reporting ✅

- [x] GitHub Actions `windows.yml` runs full matrix on Windows runners
- [x] Artifacts uploaded to workflow run (JSON, Markdown, HTML)
- [x] `report.py` generates Markdown summary from JSON results
- [x] `html_report.py` generates self-contained HTML report
- [x] `docs/findings/` populated with per-run findings
- [x] `docs.yml` deploys docs to GitHub Pages using mkdocs-material

---

## Scenario Matrix

See [`scenario-matrix.md`](scenario-matrix.md) for the full table.

---

## Key Design Decisions

1. **Data-driven scenarios** — scenario definitions live in `matrix.py` as plain Python objects, not embedded in test code.
2. **Hard evidence** — every scenario emits a JSON artifact; nothing is claimed without a recorded result.
3. **Windows first** — PE inspection, process tree capture, and console detection are Windows-specific; non-Windows runs are skipped gracefully.
4. **No shell indirection** — processes are spawned directly, not through `cmd.exe` or PowerShell, unless a scenario explicitly tests shell behavior.
5. **Rust shim** — `pyshim-win` is compiled as a GUI-subsystem executable so it never opens its own console window.
