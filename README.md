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

## Scenario Matrix

The table below summarizes every launch scenario tested by this lab. For full
details including CI results, see the
[rendered scenario matrix](https://joelvaneenwyk.github.io/py-launch-lab/scenario-matrix/).

### Direct Python / PythonW

| Scenario | Command | Subsystem | Spawns Terminal? | stdout/stderr | Notes |
|----------|---------|-----------|-----------------|---------------|-------|
| `python-script-py` | `python hello.py` | CUI | Yes | Available | Standard console launch |
| `python-script-pyw` | `python hello.pyw` | CUI | Yes | Available | py launcher may invoke pythonw (Windows-only) |
| `pythonw-script-py` | `pythonw hello.py` | GUI | No | Unavailable | GUI subsystem, no console window (Windows-only) |
| `pythonw-script-pyw` | `pythonw hello.pyw` | GUI | No | Unavailable | GUI subsystem, no console window (Windows-only) |

### uv / uvw

| Scenario | Command | Subsystem | Spawns Terminal? | stdout/stderr | Notes |
|----------|---------|-----------|-----------------|---------------|-------|
| `uv-run-script-py` | `uv run hello.py` | CUI | Yes | Available | uv is a CUI executable |
| `uv-run-script-pyw` | `uv run hello.pyw` | CUI | Yes | Available | uv runs .pyw with python, not pythonw |
| `uv-run-gui-script` | `uv run --gui-script hello.py` | GUI | No | Unavailable | Uses GUI subsystem launcher (Windows-only) |
| `uvw-run-script-py` | `uvw run hello.py` | GUI | No | Unavailable | uvw is the GUI counterpart of uv (Windows-only) |

### uvx / uv tool

| Scenario | Command | Subsystem | Spawns Terminal? | stdout/stderr | Notes |
|----------|---------|-----------|-----------------|---------------|-------|
| `uvx-pkg-console` | `uvx --from pkg lab-console` | CUI | Yes | Available | Tool run with console entrypoint |
| `uv-tool-run-pkg-console` | `uv tool run --from pkg lab-console` | CUI | Yes | Available | Equivalent to uvx |
| `uv-tool-install-console` | `uv tool install pkg_console` | CUI | Yes | Available | Installed console entrypoint |
| `uv-tool-install-gui` | `uv tool install pkg_gui` | GUI | No | Unavailable | Installed GUI entrypoint (Windows-only) |

### Rust Shim (`pyshim-win`)

| Scenario | Command | Subsystem | Spawns Terminal? | stdout/stderr | Notes |
|----------|---------|-----------|-----------------|---------------|-------|
| `shim-python-script-py` | `pyshim-win --hide-console -- python hello.py` | GUI | No | Forwarded | GUI shim hides console (Windows-only) |
| `shim-uv-run-script-py` | `pyshim-win --hide-console -- uv run hello.py` | GUI | No | Forwarded | GUI shim wrapping uv (Windows-only) |

### Key Terminology

- **CUI** (Console User Interface): PE subsystem value 3 (`IMAGE_SUBSYSTEM_WINDOWS_CUI`). Inherits or creates a console window.
- **GUI** (Graphical User Interface): PE subsystem value 2 (`IMAGE_SUBSYSTEM_WINDOWS_GUI`). No console attached by default.
- **Spawns Terminal?**: Whether the launcher causes a visible `conhost.exe` / terminal window to appear when launched from a non-console context (e.g., Explorer, Task Scheduler).

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

🚧 **M0 -- Skeleton complete.** Module stubs, fixtures, Rust crate, and CI skeletons are in place.

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

## Documentation

Full rendered documentation is available at
**<https://joelvaneenwyk.github.io/py-launch-lab/>** and includes:

- [Architecture Overview](https://joelvaneenwyk.github.io/py-launch-lab/overview/)
- [Windows Launch Semantics](https://joelvaneenwyk.github.io/py-launch-lab/windows-launch-semantics/)
- [Scenario Matrix](https://joelvaneenwyk.github.io/py-launch-lab/scenario-matrix/)
- [CI Findings](https://joelvaneenwyk.github.io/py-launch-lab/findings/report/)
- [Project Plan](https://joelvaneenwyk.github.io/py-launch-lab/plan/)

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
