# Milestone M3 — uv and uvw Scenario Coverage

> Issue: TBD

## Description

Extend the test matrix to cover all `uv` and `uvw` launch modes. This includes `uv run`, `uvx`, `uv tool run`, and `uv tool install` for both console and GUI fixture packages, producing per-scenario JSON evidence artifacts.

## How it Works

1. Each `uv`/`uvw` invocation pattern is defined as a scenario in the matrix
2. The runner executes each scenario and records observable behaviour
3. Results are serialised to `artifacts/json/` as per-scenario JSON files
4. Integration tests validate expected outcomes for each launch mode

## Tasks

- [ ] Run scenarios for `uv run script.py`, `uv run script.pyw`, `uv run --gui-script`
- [ ] Run scenarios for `uvx` and `uv tool run`
- [ ] Run `uv tool install` for console and GUI fixture packages
- [ ] Integration tests: `test_uv_run.py`, `test_uv_tool_install.py`, `test_uvx.py`, `test_uvw.py`
- [ ] Populate `artifacts/json/` with per-scenario result JSON

## Related Issues

- Depends on [m2-python-vs-pythonw-launch.md](m2-python-vs-pythonw-launch.md) - needs the process runner infrastructure

## Next Steps

- [ ] Verify `uv` and `uvw` are available on the CI Windows runner
- [ ] Confirm fixture packages install cleanly via `uv tool install`
- [ ] Review JSON artifacts for completeness and schema compliance
