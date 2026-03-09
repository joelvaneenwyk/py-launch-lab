# Python Launch Lab

> Windows-first conformance and evidence-gathering lab for Python launch modes.

## Purpose

**Python Launch Lab** (`py-launch-lab`) systematically measures how Python code is launched across every major invocation path on Windows:

- `python` and `pythonw`
- `uv`, `uvw`, `uvx`
- `uv run`, `uv tool run`, `uv tool install`
- project `.venv` direct execution
- raw `.py` and `.pyw` files
- `[project.scripts]` and `[project.gui-scripts]` entrypoints
- a reusable Rust shim (`pyshim-win`) that is itself a GUI-subsystem executable

The primary question this repo answers:

> *"What executable actually launches, what subsystem does it use, and does it create or show a terminal window under real Windows conditions?"*

## Scope

**In scope:**
- Observable behavior of launchers on Windows
- PE header inspection (console vs GUI subsystem)
- Process tree and console window detection
- Stdout/stderr availability
- Structured, machine-readable evidence artifacts

**Out of scope:**
- Internals of `uv`, CPython, or any launcher
- Non-Windows platform guarantees
- Anything not directly observable from the outside

## Current Status

🚧 **M0 — Skeleton complete.** Module stubs, fixtures, Rust crate, and CI skeletons are in place. No real measurements yet.

See [plan.md](plan.md) for milestone details.

## Directory Map

```
py-launch-lab/
├── src/launch_lab/       # Python orchestrator package
│   ├── cli.py            # Typer-based CLI (py-launch-lab)
│   ├── models.py         # Pydantic result schema
│   ├── matrix.py         # Scenario definitions
│   ├── runner.py         # Process spawner and observer
│   ├── inspect_pe.py     # Windows PE header reader
│   ├── detect_windows.py # Console/window detection
│   ├── collect.py        # Artifact collector
│   ├── report.py         # Report builder
│   └── util.py           # Shared utilities
├── tests/                # Unit and integration tests
├── fixtures/             # Small test packages and scripts
├── crates/pyshim-win/    # Rust GUI-subsystem shim
├── docs/                 # Documentation and findings
├── artifacts/            # Machine-readable results (gitignored except samples)
├── tools/                # PowerShell helper scripts
└── .github/workflows/    # CI pipelines
```

## Quick Start

```powershell
# Windows — install uv first: https://docs.astral.sh/uv/
uv sync --extra dev
py-launch-lab --help
py-launch-lab matrix run
py-launch-lab report build
```

```bash
# Non-Windows (limited — most scenarios require Windows)
uv sync --extra dev
py-launch-lab --help
```

## Planned Milestones

| Milestone | Description | Status |
|-----------|-------------|--------|
| M0 | Repo skeleton | ✅ Done |
| M1 | Static PE inspection | 🔲 Planned |
| M2 | Python vs PythonW validation | 🔲 Planned |
| M3 | uv / uvw scenario coverage | 🔲 Planned |
| M4 | Rust shim integration | 🔲 Planned |
| M5 | CI artifacts and reporting | 🔲 Planned |

## Windows Focus

This repo targets Windows because that is where Python launch behavior is most surprising and least documented. Console vs GUI subsystem, `conhost.exe` attachment, and hidden-window tricks all behave differently on Windows than on Unix. Non-Windows CI is included only to catch import errors and schema regressions.

## Contributing

See [docs/overview.md](docs/overview.md) for architecture notes. Open an issue before adding new scenarios.
