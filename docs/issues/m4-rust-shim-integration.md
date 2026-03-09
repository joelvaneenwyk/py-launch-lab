# Milestone M4 — Rust Shim Integration

> Issue: TBD

## Description

Build and integrate the `pyshim-win` Rust crate as a GUI-subsystem executable that can launch Python processes without opening its own console window. The shim resolves interpreters on PATH, detects subsystem types at runtime, and emits structured JSON results.

## How it Works

1. `pyshim-win` is compiled as a Windows GUI-subsystem executable (no console window)
2. It resolves `python`, `pythonw`, `uv`, `uvw` on the system PATH
3. It spawns child processes using `CreateProcess` with appropriate flags
4. At runtime it detects whether the target is a console or GUI executable
5. It emits a structured JSON result for each invocation

## Tasks

- [ ] Implement `pyshim-win` CLI with `--hide-console` flag
- [ ] Implement `launch.rs`: spawn child process using `CreateProcess` with appropriate flags
- [ ] Implement `resolve.rs`: locate `python`, `pythonw`, `uv`, `uvw` on PATH
- [ ] Implement `detect.rs`: detect console vs GUI subsystem at runtime
- [ ] Emit structured JSON result from shim
- [ ] Integration test: `test_shim.py`

## Related Issues

- Depends on [m1-static-pe-inspection.md](m1-static-pe-inspection.md) - shares PE subsystem classification concepts

## Next Steps

- [ ] Cross-compile or build on a Windows runner
- [ ] Verify the shim does not flash a console window when launched
- [ ] Confirm JSON output matches the project schema
