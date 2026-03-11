# Python Launch Lab

> Windows-first conformance and evidence-gathering lab for Python launch modes.

## What is this?

**Python Launch Lab** (`py-launch-lab`) systematically measures how Python code
is launched across every major invocation path on Windows. It records
machine-readable evidence about PE subsystem types, console window creation,
and stdout/stderr availability for each launcher.

## Quick Start

```powershell
# Windows — install uv first: https://docs.astral.sh/uv/
uv sync --extra dev
py-launch-lab --help
py-launch-lab matrix run
py-launch-lab report build
```

## Key Question

> *"What executable actually launches, what subsystem does it use, and does it
> create or show a terminal window under real Windows conditions?"*

## Launchers Tested

| Launcher | Type | Description |
|----------|------|-------------|
| `python` | CUI | Standard CPython console interpreter |
| `pythonw` | GUI | Windowless CPython interpreter |
| `uv` | CUI | Astral's fast Python package manager |
| `uvw` | GUI | GUI-subsystem counterpart of `uv` |
| `uvx` | CUI | Shorthand for `uv tool run` |
| `pyshim-win` | GUI | Custom Rust shim with `--hide-console` support |

## Documentation

- **[Architecture Overview](overview.md)** -- Components and data flow
- **[Scenario Matrix](scenario-matrix.md)** -- All test scenarios with expected behavior
- **[Windows Launch Semantics](windows-launch-semantics.md)** -- CUI vs GUI, console attachment, creation flags
- **[CI Findings](findings/report.md)** -- Latest results from CI runs
- **[Project Plan](plan.md)** -- Milestones and roadmap

## Source Code

The source code is available on [GitHub](https://github.com/joelvaneenwyk/py-launch-lab).
