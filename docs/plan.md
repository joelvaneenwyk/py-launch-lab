# Python Launch Lab — Project Plan

## Overview

This lab systematically measures how Python launch modes behave on Windows across every major launcher and packaging mechanism. Each scenario is run, inspected, and recorded as machine-readable evidence.

---

## Milestone M0 — Repo Skeleton ✅

- [x] Repository structure created
- [x] `pyproject.toml` with `launch_lab` package and `py-launch-lab` CLI
- [x] Python module stubs: `cli`, `models`, `matrix`, `runner`, `inspect_pe`, `detect_windows`, `collect`, `report`, `util`
- [x] Fixture directories: `pkg_console`, `pkg_gui`, `pkg_dual`, `raw_py`, `raw_pyw`, `direct_exec`
- [x] Rust crate `pyshim-win` stub compiling on Windows
- [x] GitHub Actions CI skeleton (`windows.yml`, `docs.yml`)
- [x] Basic unit tests: schema, matrix generation, importability

---

## Milestone M1 — Static PE Inspection

- [ ] Implement `inspect_pe.py`: read PE header from any Windows EXE
- [ ] Classify `IMAGE_SUBSYSTEM_WINDOWS_GUI` vs `IMAGE_SUBSYSTEM_WINDOWS_CUI`
- [ ] Support inspection of Python, PythonW, uv, uvw executables
- [ ] Store `pe_subsystem` field in result objects
- [ ] Unit tests for PE inspection against known executables

---

## Milestone M2 — Direct Python vs PythonW Launch Validation

- [ ] Implement `runner.py`: spawn child processes with controlled environment
- [ ] Detect whether spawned process opens a console window
- [ ] Detect `conhost.exe` appearing in process tree
- [ ] Record `stdout_available`, `stderr_available`, `visible_window_detected`
- [ ] Implement integration tests: `test_python_vs_pythonw.py`
- [ ] Capture evidence artifacts for `python script.py` vs `pythonw script.py`

---

## Milestone M3 — uv and uvw Scenario Coverage

- [ ] Run scenarios for `uv run script.py`, `uv run script.pyw`, `uv run --gui-script`
- [ ] Run scenarios for `uvx` and `uv tool run`
- [ ] Run `uv tool install` for console and GUI fixture packages
- [ ] Integration tests: `test_uv_run.py`, `test_uv_tool_install.py`, `test_uvx.py`, `test_uvw.py`
- [ ] Populate `artifacts/json/` with per-scenario result JSON

---

## Milestone M4 — Rust Shim Integration

- [ ] Implement `pyshim-win` CLI with `--hide-console` flag
- [ ] Implement `launch.rs`: spawn child process using `CreateProcess` with appropriate flags
- [ ] Implement `resolve.rs`: locate `python`, `pythonw`, `uv`, `uvw` on PATH
- [ ] Implement `detect.rs`: detect console vs GUI subsystem at runtime
- [ ] Emit structured JSON result from shim
- [ ] Integration test: `test_shim.py`

---

## Milestone M5 — CI Artifacts and Reporting

- [ ] GitHub Actions `windows.yml` runs full matrix on Windows runners
- [ ] Artifacts uploaded to workflow run
- [ ] `report.py` generates Markdown summary from JSON results
- [ ] `docs/findings/` populated with per-run findings
- [ ] `docs.yml` deploys docs to GitHub Pages

---

## Scenario Matrix

See `docs/scenario-matrix.md` for the full table.

---

## Key Design Decisions

1. **Data-driven scenarios** — scenario definitions live in `matrix.py` as plain Python objects, not embedded in test code.
2. **Hard evidence** — every scenario emits a JSON artifact; nothing is claimed without a recorded result.
3. **Windows first** — PE inspection, process tree capture, and console detection are Windows-specific; non-Windows runs are skipped gracefully.
4. **No shell indirection** — processes are spawned directly, not through `cmd.exe` or PowerShell, unless a scenario explicitly tests shell behavior.
5. **Rust shim** — `pyshim-win` is compiled as a GUI-subsystem executable so it never opens its own console window.
