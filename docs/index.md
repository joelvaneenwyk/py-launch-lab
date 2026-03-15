# Python Launch Lab

> Windows-first conformance and evidence-gathering lab for Python launch modes.

## Interactive Report

The **interactive HTML report** is the primary output of this project and is
the **default landing page** of the deployed site. It shows the most recent CI
run results for both the **official uv release** and the **custom
`joelvaneenwyk/uv` build** side by side, with filters, sorting, and anomaly
explanations.

[**:material-chart-bar: Open Interactive Report &rarr;**](report.md){ .md-button .md-button--primary }
[**:material-file-find: View CI Findings (Markdown)**](findings/report.md){ .md-button }

!!! tip "The report is the landing page"
    When the CI pipeline runs successfully, the site homepage automatically
    redirects to the interactive report. Use the **uv Version** column filter
    to compare official vs. custom uv results.

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
- **[Implementation Guide](implementation.md)** -- How detection, reporting, and AI integration work
- **[Detection Deep Dive](detection-deep-dive.md)** -- Low-level Windows process and window detection
- **[Findings & Anomalies](findings/anomalies.md)** -- What we found, root causes, upstream issues
- **[CI Findings](findings/report.md)** -- Latest results from CI runs
- **[Development History](development-history.md)** -- What worked, what didn't, and why
- **[Project Plan](plan.md)** -- Milestones and roadmap

## Source Code

The source code is available on [GitHub](https://github.com/joelvaneenwyk/py-launch-lab).
