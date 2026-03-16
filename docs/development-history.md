# Development History

This document chronicles the evolution of py-launch-lab — the problems
we set out to solve, the approaches that worked, the ones that didn't,
and the iterative discoveries that shaped the final implementation.

---

## Phase 1: Initial Report System Overhaul

### The Starting Point

The original report system generated per-launcher sections in a static
HTML file.  Each launcher (`python`, `uv`, `venv-direct`, etc.) had its
own table.  The report had no filtering, no sorting, and no way to
identify which results were **unexpected**.

### What We Changed

Eight major features were implemented in a single pass:

#### 1. Command Line Column

**Problem:** The report showed scenario IDs and launcher names, but not
the actual command that was executed.

**Solution:** Added a `command_line: list[str] | None` field to the
`ScenarioResult` Pydantic model.  The `runner.py` populates it with the
exact `cmd` list.  The HTML report converts absolute paths to
project-relative paths for readability.

```python
# Before: /home/user/project/.cache/matrix_venv/Scripts/python.exe
# After:  .cache/matrix_venv/Scripts/python.exe
```

#### 2. Anomaly Highlighting with Explanation Bubbles

**Problem:** Results were displayed without context — the reader had no
way to know if a result was expected or surprising.

**Solution:** Created `expectations.py` with per-scenario expected
behaviours and a `check_expectations()` function that produces `Anomaly`
objects.  The HTML report highlights anomaly rows with a red tint and
shows expandable detail rows with:
- Which fields deviate
- Expected vs actual values
- Technical explanation
- Link to upstream issues

#### 3. Single Unified Table

**Problem:** Per-launcher sections made it hard to compare results across
different launchers.

**Solution:** Removed the per-launcher split entirely.  All 20 scenarios
appear in one table, sorted by scenario ID.  A "Launcher" column lets you
see the launcher for each row.

#### 4. Column Filters

**Problem:** With 20 rows in one table, users need to filter by launcher,
subsystem, etc.

**Solution:** Added a filter row below the header with dropdown selectors
for enum columns (Launcher, PE Subsystem, Console Window, etc.) and text
inputs for free-form columns.  Filtering is done entirely in client-side
JavaScript.

#### 5. Sortable Column Headers

Click any header to sort ascending/descending.  JavaScript-based,
no server round-trip.

#### 6. Verbose Logging

**Problem:** `task report` was a black box — no output about what it was
doing.

**Solution:** Added `_setup_logging(verbose=True)` to the CLI.  The
report builder now emits detailed logs:

```
14:23:01 [launch_lab.html_report] INFO: HTML report builder starting
14:23:01 [launch_lab.html_report] INFO:   JSON source dir : E:\...\artifacts\json
14:23:01 [launch_lab.html_report] INFO:   Output dir      : E:\...\artifacts\html
14:23:01 [launch_lab.html_report] INFO:   Force rebuild   : True
14:23:01 [launch_lab.html_report] INFO: Loading JSON artifacts ...
14:23:01 [launch_lab.html_report] INFO:   Loaded 20 results
14:23:01 [launch_lab.html_report] INFO:   3 scenarios have anomalies
14:23:01 [launch_lab.html_report] INFO: Attempting to generate AI summary via Ollama …
14:23:15 [launch_lab.html_report] INFO: Ollama summary generated successfully (1423 chars).
14:23:15 [launch_lab.html_report] INFO: Report written to artifacts\html\report.html
```

#### 7. `--force` Flag

**Problem:** The report builder skipped regeneration if the output file
was newer than all JSON inputs.  During development, you often want to
force a rebuild.

**Solution:** Added `--force` flag to the CLI.  Also updated `taskfile.yaml`
to forward a `FORCE` variable: `task report FORCE=1`.

#### 8. Ollama AI Integration

**Problem:** Interpreting 20 scenario results requires domain expertise.

**Solution:** Optionally call a local Ollama instance to generate a
natural-language summary.  The summary is inserted at the top of the
HTML report.  Configuration via environment variables:

- `OLLAMA_MODEL` (default: `llama3.2`)
- `OLLAMA_HOST` (default: `http://localhost:11434`)

Uses `curl` to avoid adding a `requests` dependency.

---

## Phase 2: Fixing N/A Values

### The Problem

After the initial overhaul, many scenarios showed "N/A" for Console Window
and Visible Window in the report.  Affected scenarios:

- All `uv` / `uvx` / `uvw` scenarios
- All `shim` scenarios
- Most `venv` scenarios

### Root Cause

The original `_try_keepalive_detection()` function only handled Python-like
executables.  It checked:

```python
if _is_python_like(exe_path):
    return [exe, "-c", "import time; time.sleep(10)"]
return None  # ← everything else returned None
```

This meant `uv`, `uvx`, `uvw`, `pyshim-win`, and venv entry-point wrappers
all exited before Phase 1 detection could observe them, and no keepalive
was attempted.

### The Fix

Expanded keepalive coverage with per-executable-type strategies:

```python
def _build_keepalive_cmd(exe: str) -> list[str] | None:
    if _is_python_like(exe):
        return [exe, "-c", "import time; time.sleep(10)"]
    if _is_uv_like(exe):
        return [exe, "run", "python", "-c", "import time; time.sleep(10)"]
    if _is_shim_like(exe):
        return [exe, "--hide-console", "--", "python", "-c", "import time; time.sleep(10)"]
    # Venv wrappers: use sibling python.exe
    if exe_has_sibling_python(exe):
        return [sibling_python, "-c", "import time; time.sleep(10)"]
    return None
```

Also added PE-subsystem inference as a final fallback for any remaining
`None` values — if we know the PE subsystem, we can infer console behaviour.

### Result

All 20 scenarios now have populated Console Window and Visible Window values.

---

## Phase 3: The lab-window-gui.exe Console Detection Bug

### The Problem

After fixing N/A values, the report showed `venv-gui-entrypoint`
(`.cache/matrix_venv/Scripts/lab-window-gui.exe`) with `Console Window = No`.

The user knew this was wrong — **launching `lab-window-gui.exe` absolutely opens
a terminal window** (visible as a brief flash on the desktop).

### Investigation

`lab-window-gui.exe` is a pip/uv-generated GUI entry-point wrapper:
- **Wrapper PE subsystem:** GUI ← this is correct
- **Expected behaviour:** No console window ← this is the ideal behaviour

But in practice, a console DOES appear.  Why?

#### The Discovery

The wrapper internally launches the venv's `pythonw.exe` to call the
entry-point function.  In a standard `python -m venv`, `pythonw.exe` is
a genuine GUI binary — no console.

But in a **uv venv**, `pythonw.exe` is a **CUI trampoline**.  Its PE
subsystem is `IMAGE_SUBSYSTEM_WINDOWS_CUI` (value 3) instead of
`IMAGE_SUBSYSTEM_WINDOWS_GUI` (value 2).

When the GUI wrapper spawns this CUI `pythonw.exe`, Windows allocates a
console window for the child process.  This console window briefly appears
and then disappears when the script completes — the "terminal flash".

This is [astral-sh/uv#9781](https://github.com/astral-sh/uv/issues/9781),
under active investigation at [joelvaneenwyk/uv#1](https://github.com/joelvaneenwyk/uv/issues/1)
with a fix in progress at [joelvaneenwyk/uv#2](https://github.com/joelvaneenwyk/uv/pull/2).

#### Why Direct Detection Missed It

1. `detect_console_host(lab_gui_pid)` returned `False` because `conhost.exe`
   is a child of `pythonw.exe`, not `lab-window-gui.exe`.  The process tree
   query only returns direct children.

2. Inference from PE subsystem said "GUI → no console" because the
   **wrapper** is GUI.  But it's the **child** that determines console
   allocation.

3. Keepalive detection used the sibling `python.exe` (CUI), which
   correctly showed a console.  But this was for the sibling, not for
   what `lab-window-gui.exe` actually does.

### The Fix

Added `_detect_child_python_subsystem()`:

1. Check if the executable is a venv wrapper (not python, not uv, not shim;
   has a sibling `python.exe`)
2. If it's a GUI wrapper → inspect the PE of `pythonw.exe` in the same
   `Scripts/` directory
3. If it's a CUI wrapper → inspect the PE of `python.exe`
4. Return the child's PE subsystem

Then in `run_scenario()`, apply the override:

```python
child_sub = _detect_child_python_subsystem(cmd[0])
if pe_subsystem == "GUI" and child_sub == "CUI":
    console_window = True  # CUI child WILL allocate a console
```

### Result

The report now correctly shows:

| Scenario | PE | Console Window | Anomaly? |
|----------|-----|----------------|----------|
| `venv-gui-entrypoint` | GUI | **Yes** | Yes — uv#9781 |
| `venv-dual-gui-entrypoint` | GUI | **Yes** | Yes — uv#9781 |
| `venv-pythonw-script-py` | **CUI** | Yes | Yes — uv#9781 |

All three anomalies are correctly flagged with explanations linking to
the upstream uv issue.

---

## Key Lessons Learned

### 1. "What the binary says" vs "What actually happens"

The PE subsystem tells you what a binary **claims** to be.  But what
**actually happens** on screen depends on the entire process tree.
A GUI binary can cause a console to appear if it spawns a CUI child.

### 2. You can't test window creation with pipes

Any test harness that redirects stdout/stderr via pipes will **never**
see a console window.  The pipe handles satisfy the CUI process's console
requirement without allocating a visible window.  Phase 1 (no pipes)
was essential.

### 3. Process tree queries are point-in-time

`CreateToolhelp32Snapshot` gives you the state at the instant you call it.
If a process exits 10 ms later, the snapshot won't reflect that.  If a
process hasn't spawned yet, the snapshot won't show it.  Multiple
detection strategies (direct, keepalive, PE inspection) provide
overlapping coverage.

### 4. Deterministic checks beat timing-based checks

The child PE subsystem override is deterministic — it reads files on
disk, not transient process state.  It's the most reliable detection
method.  If we know the child interpreter is CUI, we know a console will
appear.  No timing, no race conditions.

### 5. Upstream bugs surface as test failures

The entire uv pythonw CUI trampoline issue (uv#9781) was discovered
because our tests reported unexpected console behaviour.  This is
exactly what a conformance lab is supposed to find.

### 6. The keepalive trick is essential but imperfect

Re-launching an executable with `sleep(10)` is a great hack for detection,
but it tests "what would this executable do if kept alive", not "what does
the original command do".  For most scenarios these are equivalent, but
be aware of the distinction.

---

## Timeline

| Phase | Focus | Scenarios Affected | Outcome |
|-------|-------|-------------------|---------|
| 1 | Report overhaul | All 20 | 8 features implemented |
| 2 | N/A value fix | ~12 scenarios | All values populated |
| 3 | Console detection fix | 3 venv scenarios | Correct anomaly detection |

---

## Files Changed

| File | Changes |
|------|---------|
| `src/launch_lab/models.py` | Added `command_line` field |
| `src/launch_lab/expectations.py` | **New file** — expected behaviours & anomaly checker |
| `src/launch_lab/html_report.py` | Complete rewrite — unified table, filters, anomalies, Ollama |
| `src/launch_lab/runner.py` | Keepalive strategies, child PE detection, inference fallback |
| `src/launch_lab/cli.py` | `--force` flag, verbose logging setup |
| `taskfile.yaml` | FORCE variable forwarding |
| `tests/test_html_report.py` | Updated for new API, anomaly/filter tests |
