# Findings & Anomalies

This document records the key findings from running the py-launch-lab
scenario matrix on Windows, including anomalies discovered, root causes
identified, and upstream issues referenced.

---

## Summary

Out of 20 scenarios tested, **3 consistently produce anomalies** — all
related to the same upstream bug in `uv` where venv `pythonw.exe` is
created as a CUI (console) binary instead of a GUI binary.

| Scenario | Anomaly | Root Cause |
|----------|---------|------------|
| `venv-gui-entrypoint` | Console Window: expected No, got Yes | uv venv pythonw.exe is CUI |
| `venv-dual-gui-entrypoint` | Console Window: expected No, got Yes | uv venv pythonw.exe is CUI |
| `venv-pythonw-script-py` | PE Subsystem: expected GUI, got CUI | uv venv pythonw.exe is CUI |

---

## The uv pythonw.exe Problem (uv#9781)

!!! bug "uv venv creates CUI pythonw.exe"

    **Upstream Issue:** [astral-sh/uv#9781](https://github.com/astral-sh/uv/issues/9781)
    **Investigation:** [joelvaneenwyk/uv#1](https://github.com/joelvaneenwyk/uv/issues/1)
    **Fix PR (in progress):** [joelvaneenwyk/uv#2](https://github.com/joelvaneenwyk/uv/pull/2)

    When `uv venv` creates a virtual environment, it does **not** copy the
    real GUI-subsystem `pythonw.exe`.  Instead, it generates a CUI trampoline —
    a small console-subsystem executable that internally launches the base
    interpreter.

### Expected vs Actual

| venv Tool | pythonw.exe PE Subsystem | Console Window? |
|-----------|------------------------|--------------------|
| `python -m venv` | GUI | No |
| `uv venv` | **CUI** (trampoline) | **Yes** |

### Downstream Effects

This single bug causes cascading issues:

1. **`pythonw.exe` scripts flash a terminal.**
   Running `venv/Scripts/pythonw.exe hello.py` opens a console window
   that immediately closes — visible as a "terminal flash" on the desktop.

2. **GUI entry-point wrappers also flash a terminal.**
   pip/uv-generated GUI wrappers (e.g. `lab-window-gui.exe`) invoke `pythonw.exe`
   internally.  Because the child `pythonw.exe` is CUI, Windows allocates
   a console for the child process even though the wrapper itself is GUI.

3. **The "no console" promise of `[project.gui-scripts]` is broken.**
   Packages that define `[project.gui-scripts]` in `pyproject.toml` expect
   their entry-points to launch silently.  In a `uv venv`, they don't.

### How py-launch-lab Detects This

The runner uses `_detect_child_python_subsystem()` to inspect the PE
subsystem of the interpreter that a venv wrapper will invoke:

```python
def _detect_child_python_subsystem(exe: str) -> str | None:
    # Check if the exe is a venv wrapper (has sibling python.exe)
    # GUI wrappers → check pythonw.exe PE subsystem
    # CUI wrappers → check python.exe PE subsystem
    ...
```

When a GUI wrapper's child interpreter is CUI, the runner overrides
`console_window = True` regardless of what direct detection reported,
because the console allocation is deterministic (it always happens).

---

## Findings by Launcher Category

### python / pythonw (Direct)

All 4 scenarios behave as expected:

| Scenario | PE | Console | stdout | Status |
|----------|-----|---------|--------|--------|
| `python-script-py` | CUI | Yes | Yes | OK |
| `python-script-pyw` | CUI | Yes | No | OK |
| `pythonw-script-py` | GUI | No | Yes | OK |
| `pythonw-script-pyw` | GUI | No | No | OK |

`python.exe` is CUI: always allocates a console.
`pythonw.exe` is GUI: never allocates a console.
The `.py` vs `.pyw` extension affects stdout availability but not console
creation — that's determined solely by the launcher's PE subsystem.

### uv run

| Scenario | PE | Console | stdout | Status |
|----------|-----|---------|--------|--------|
| `uv-run-script-py` | CUI | Yes | Yes | OK |
| `uv-run-script-pyw` | CUI | Yes | No | OK |
| `uv-run-gui-script` | CUI | Yes | Yes | OK |

All three work as expected.  Note that `uv run --gui-script` is intended
to suppress the console, but because `uv.exe` itself is CUI, Windows
still allocates a console.  This is a known `uv` limitation — the flag
only affects the *child* process, not the parent launcher.

### uvw

| Scenario | PE | Console | stdout | Status |
|----------|-----|---------|--------|--------|
| `uvw-run-script-py` | GUI | No | Yes | OK |

`uvw.exe` is the GUI counterpart to `uv.exe`, mirroring the `python`/`pythonw`
split.  No console is allocated.

### uvx / uv tool

| Scenario | PE | Console | stdout | Status |
|----------|-----|---------|--------|--------|
| `uvx-pkg-console` | CUI | Yes | Yes | OK |
| `uv-tool-run-pkg-console` | CUI | Yes | Yes | OK |
| `uv-tool-install-console` | CUI | Yes | No | OK |
| `uv-tool-install-gui` | CUI | Yes | No | OK |

Tool install commands produce no stdout (progress goes to stderr).

### venv-direct

| Scenario | PE | Console | stdout | Status |
|----------|-----|---------|--------|--------|
| `venv-python-script-py` | CUI | Yes | Yes | OK |
| `venv-pythonw-script-py` | **CUI** | Yes | Yes | **ANOMALY** |
| `venv-console-entrypoint` | CUI | Yes | Yes | OK |
| `venv-gui-entrypoint` | GUI | **Yes** | No | **ANOMALY** |
| `venv-dual-console-entrypoint` | CUI | Yes | Yes | OK |
| `venv-dual-gui-entrypoint` | GUI | **Yes** | No | **ANOMALY** |

The three anomalies are all caused by the uv pythonw.exe CUI trampoline
problem described above.

### pyshim-win (Rust shim)

| Scenario | PE | Console | stdout | Status |
|----------|-----|---------|--------|--------|
| `shim-python-script-py` | GUI | No | Yes | OK |
| `shim-uv-run-script-py` | GUI | No | Yes | OK |

The Rust shim successfully suppresses console windows by using
`CREATE_NO_WINDOW` when spawning child processes.  Despite `python.exe`
and `uv.exe` being CUI binaries, the shim prevents console allocation.

---

## What Worked Well

1. **Two-phase detection is reliable.**
   Separating window/console detection (Phase 1, no pipes) from output
   capture (Phase 2, with pipes) was essential.  Pipes suppress console
   allocation, so a single-phase approach would never detect consoles.

2. **PE inspection is deterministic.**
   Reading the PE header directly is much more reliable than heuristics
   like "does the name contain 'w'?".  It correctly handles edge cases
   like uv's CUI pythonw trampoline.

3. **Keepalive strategy covers fast-exiting processes.**
   `uv tool install`, `uvx`, and venv wrapper tests all exit in <100ms.
   Re-launching with a sleep command gives detection enough time to snapshot
   the process tree.

4. **Child PE inspection catches the uv bug.**
   Without `_detect_child_python_subsystem()`, GUI entry-point wrappers
   would report `console_window = False` (because direct detection misses
   the briefly-appearing console).  The child PE override catches this
   deterministically.

---

## What Didn't Work

1. **Direct detection alone is unreliable for fast processes.**
   Even with aggressive polling (10 × 50 ms), many processes exit before
   `CreateToolhelp32Snapshot` can capture them.  The keepalive fallback
   was necessary.

2. **`conhost.exe` detection misses GUI wrapper children.**
   When `lab-window-gui.exe` (GUI wrapper) launches `pythonw.exe` (CUI in uv venvs),
   `conhost.exe` appears as a child of `pythonw.exe`, not `lab-window-gui.exe`.
   Since `get_process_tree()` only captures direct children,
   `detect_console_host()` returns False.  The child PE override was
   needed to compensate.

3. **`uv run --gui-script` doesn't prevent console allocation.**
   The `--gui-script` flag only affects the child process (it uses
   `pythonw` instead of `python`).  Since `uv.exe` itself is CUI,
   Windows allocates a console for `uv.exe` before the child is spawned.

4. **Timing sensitivity.**
   Process tree snapshots are inherently racy.  A process can exit between
   the `Popen()` call and the `CreateToolhelp32Snapshot()` call.  The
   keepalive strategy mitigates this, but the fundamental problem remains.

---

## Upstream Issues Referenced

| Issue | Description | Impact |
|-------|-------------|--------|
| [astral-sh/uv#9781](https://github.com/astral-sh/uv/issues/9781) | uv venv pythonw.exe is CUI trampoline | 3 scenario anomalies |
| [joelvaneenwyk/uv#1](https://github.com/joelvaneenwyk/uv/issues/1) | Investigation and reproduction of the bug | Documents root cause |
| [joelvaneenwyk/uv#2](https://github.com/joelvaneenwyk/uv/pull/2) | Fix PR in progress | Pending upstream review |
