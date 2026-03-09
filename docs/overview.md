# Python Launch Lab — Architecture Overview

## Goals

The lab answers one primary question for each scenario:

> *What executable actually launches, what subsystem does it use, and does it
> create or show a terminal window under real Windows conditions?*

## Components

### Python Orchestrator (`src/launch_lab/`)

| Module | Responsibility |
|--------|----------------|
| `cli.py` | Typer-based CLI (`py-launch-lab`) |
| `models.py` | Pydantic result schema |
| `matrix.py` | Scenario definitions (data, not logic) |
| `runner.py` | Process spawner and observer |
| `inspect_pe.py` | PE header reader |
| `detect_windows.py` | Console / window detection (Windows-only) |
| `collect.py` | Artifact writer and reader |
| `report.py` | Markdown report builder |
| `util.py` | Shared utilities |

### Rust Shim (`crates/pyshim-win/`)

A Windows GUI-subsystem executable that can launch children with controlled
console visibility.  Built with Cargo; the binary is placed on PATH during CI.

### Fixtures (`fixtures/`)

Minimal Python packages and scripts that serve as well-defined targets for
each scenario.  They are intentionally small and boring.

## Data Flow

```
matrix.py ──► runner.py ──► subprocess ──► target fixture
                  │
                  ▼
            collect.py ──► artifacts/json/<id>.json
                  │
                  ▼
            report.py ──► artifacts/markdown/report.md
```

## Design Decisions

1. **Scenarios are data.** Scenario definitions live in `matrix.py` as frozen
   dataclasses.  Adding a new scenario does not require touching `runner.py`.

2. **Hard evidence.** Every scenario emits a JSON artifact before any human
   interpretation.  The report is generated *from* the artifacts.

3. **No shell indirection.** `runner.py` uses `subprocess.run` with a list
   argument, not a shell string.  Scenarios that test shell behaviour are
   explicitly marked.

4. **Graceful non-Windows.** Windows-specific modules (`detect_windows.py`,
   PE inspection of real executables) return `None` or empty lists on other
   platforms.
