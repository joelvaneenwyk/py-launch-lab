# Implementation Guide

This document describes **how py-launch-lab works** at a technical level —
the detection pipeline, data model, report generation, and AI integration.

---

## Architecture at a Glance

```
CLI (cli.py)
  ├─ matrix run   → runner.py  → subprocess → Process/Window detection
  │                                │
  │                                ▼
  │                          collect.py  → artifacts/json/<id>.json
  │
  └─ report build → html_report.py
                        ├─ load_all_results()        ← collect.py
                        ├─ check_expectations()      ← expectations.py
                        ├─ _try_ollama_summary()     ← Ollama API
                        └─ _render_html_report()     → artifacts/html/report.html
```

---

## Scenario Definitions (`matrix.py`)

Every test scenario is a frozen `@dataclass` with these fields:

| Field | Purpose |
|-------|---------|
| `scenario_id` | Unique key, used as artifact filename |
| `launcher` | Top-level executable (e.g. `python`, `uv`, `venv-direct`) |
| `mode` | Launch mode (e.g. `script.py`, `run script.pyw`) |
| `fixture` | Which fixture package or script to use |
| `args` | Command-line arguments to pass to the launcher |
| `windows_only` | Skip on non-Windows platforms |
| `requires_uv` | Skip if `uv` is not on PATH |

Adding a scenario is **data-only** — you add a `Scenario()` entry in
`matrix.py` and (optionally) an entry in `expectations.py`.  No code changes
to `runner.py` are required.

---

## The Detection Pipeline (`runner.py`)

### Two-Phase Process Observation

Each scenario is executed **twice**:

#### Phase 1 — Window and Console Detection (Windows only)

```python
detect_proc = subprocess.Popen(
    cmd,
    creationflags=subprocess.CREATE_NEW_CONSOLE,
    # NO stdout/stderr pipes — the process gets a real console
)
```

- The process is launched with `CREATE_NEW_CONSOLE` and **no pipes**.
  Pipes suppress console allocation, which would make detection useless.
- The runner polls aggressively (10 iterations × 50 ms, then 300 ms)
  for fast-exiting processes.
- If the process is still alive, it snapshots:
    - **Process tree** via `CreateToolhelp32Snapshot` (ctypes)
    - **Visible windows** via `EnumWindows` (user32)
    - **Console host** by looking for `conhost.exe` / `WindowsTerminal.exe`
      in the child process tree

#### Phase 2 — Output Capture (all platforms)

```python
proc = subprocess.Popen(cmd, stdout=PIPE, stderr=PIPE, text=True)
out, err = proc.communicate(timeout=timeout)
```

This captures `stdout`, `stderr`, and the exit code.

### Keepalive Strategy

Many processes (especially `uv`, `uvx`, `uvw`, and venv entry-point wrappers)
exit before Phase 1 can snapshot them.  When Phase 1 detects an early exit,
the runner invokes `_try_keepalive_detection()`, which re-launches the
**same executable** with a long-lived command:

| Executable Type | Keepalive Command |
|-----------------|-------------------|
| Python-like (`python`, `pythonw`) | `<exe> -c "import time; time.sleep(10)"` |
| uv-like (`uv`, `uvx`, `uvw`) | `<exe> run python -c "import time; time.sleep(10)"` |
| Shim (`pyshim-win`) | `<exe> --hide-console -- python -c "import time; time.sleep(10)"` |
| Venv wrappers | Sibling `python.exe -c "import time; time.sleep(10)"` |

The keepalive process is launched with `CREATE_NEW_CONSOLE`, observed for
800 ms, then killed.

### Inference Fallback

If direct detection and keepalive both fail (or aren't available), the
runner falls back to PE-subsystem-based inference:

- **CUI executable** → `console_window = True`, `visible_window = False`
- **GUI executable** → `console_window = False`, `visible_window = True`
  (if the scenario name/mode contains "gui")

### Child Python Subsystem Override

Venv entry-point wrappers (pip/uv-generated `.exe` files) internally
launch the venv's `python.exe` or `pythonw.exe`.  The **wrapper's** PE
subsystem may not reflect the **child interpreter's** subsystem.

The function `_detect_child_python_subsystem()`:

1. Checks if the executable is a venv wrapper (has a sibling `python.exe`
   in the same `Scripts/` directory)
2. Determines which interpreter the wrapper calls (GUI wrappers → `pythonw.exe`,
   console wrappers → `python.exe`)
3. Inspects the **child interpreter's** PE subsystem

**Critical override:** if the wrapper is GUI but the child interpreter is
CUI (as happens in uv venvs due to [uv#9781](https://github.com/astral-sh/uv/issues/9781),
under investigation at [joelvaneenwyk/uv#1](https://github.com/joelvaneenwyk/uv/issues/1)
with a fix in progress at [joelvaneenwyk/uv#2](https://github.com/joelvaneenwyk/uv/pull/2)),
the runner forces `console_window = True` because the CUI child will
trigger Windows console allocation regardless of the wrapper's subsystem.

---

## PE Inspection (`inspect_pe.py`)

Reads the PE optional header from any Windows executable using raw struct
unpacking:

```python
# Seek to PE offset (stored at 0x3C in DOS header)
f.seek(0x3C)
pe_offset = struct.unpack("<I", f.read(4))[0]

# Skip COFF header, read optional header magic
# Subsystem field is at offset 68 from optional header start
f.seek(pe_offset + 4 + 20 + 68)
subsystem = struct.unpack("<H", f.read(2))[0]
```

Returns one of: `Subsystem.GUI`, `Subsystem.CUI`, `Subsystem.NOT_PE`,
`Subsystem.UNKNOWN`, or `None` (file not found).

---

## Windows Detection (`detect_windows.py`)

Three core detection functions, all implemented via `ctypes`:

### `get_process_tree(pid)`
Uses `CreateToolhelp32Snapshot` + `Process32First`/`Process32Next` to
enumerate all processes, filters to direct children of the given PID,
and retrieves full image paths via `QueryFullProcessImageNameW`.

### `detect_console_host(pid)`
Calls `get_process_tree()` and checks for `conhost.exe`,
`WindowsTerminal.exe`, or `OpenConsole.exe` among child processes.
Returns `True` if any console host is found.

### `detect_visible_window(pid)`
Uses `EnumWindows` to iterate all top-level windows, checks each window's
owner PID via `GetWindowThreadProcessId`, and calls `IsWindowVisible`.
Returns `True` if any visible window belongs to the target process.

### `get_creation_flags(pid)`
Attempts to retrieve the creation flags used when the process was spawned.
This is recorded in the JSON artifact for forensic inspection.

---

## Expected Behaviour & Anomaly Detection (`expectations.py`)

### Expectations Dictionary

Every scenario has an `ExpectedBehaviour` definition:

```python
@dataclass(frozen=True)
class ExpectedBehaviour:
    pe_subsystem: Subsystem | None = None
    console_window: bool | None = None
    visible_window: bool | None = None
    stdout_available: bool | None = None
    exit_code: int = 0
    explanation: str = ""
    doc_url: str = ""
```

### Anomaly Checker

`check_expectations(result)` compares the actual `ScenarioResult` against
the expected behaviour field-by-field.  Any deviation produces an `Anomaly`:

```python
@dataclass
class Anomaly:
    field: str        # e.g. "Console Window"
    expected: str     # e.g. "No"
    actual: str       # e.g. "Yes"
    explanation: str  # Why this happened
    doc_url: str      # Link to upstream issue or docs
```

---

## HTML Report (`html_report.py`)

A self-contained HTML file with embedded CSS and JavaScript. Features:

### Single Unified Table
All scenarios in one table — no per-launcher sections. Columns:

| Column | Source |
|--------|--------|
| Scenario ID | `scenario_id` |
| Launcher | `launcher` |
| Mode | `mode` |
| PE Subsystem | `pe_subsystem` |
| Console Window | `console_window_detected` |
| Visible Window | `visible_window_detected` |
| stdout | `stdout_available` |
| Exit Code | `exit_code` |
| Command Line | `command_line` (relative paths) |

### Column Filters
Each column header has a filter row with dropdowns for enum columns and
text inputs for free-text columns. Filtering is done entirely in JavaScript
on the client side.

### Sortable Headers
Click any column header to sort ascending/descending.

### Anomaly Highlighting
Rows with anomalies get an `anomaly-row` CSS class (subtle red background).
Below each anomaly row, an expandable `anomaly-detail-row` shows:
- Which fields deviate from expectations
- Expected vs actual values
- An explanation of why this happened
- Links to upstream issues

### Command Line Column
Absolute paths are converted to project-relative paths for readability
(e.g. `.cache/matrix_venv/Scripts/python.exe` instead of the full path).

---

## Ollama AI Integration

The report builder optionally calls a local [Ollama](https://ollama.ai)
instance to generate a natural-language summary paragraph.

### How It Works

1. Builds a compact JSON payload summarising all scenario results and anomalies
2. Sends it to `POST /api/generate` on the local Ollama server
3. Uses `curl` (to avoid adding a `requests` dependency)
4. The AI summary is inserted at the top of the HTML report

### Configuration

| Environment Variable | Default | Purpose |
|---------------------|---------|---------|
| `OLLAMA_MODEL` | `llama3.2` | Which Ollama model to use |
| `OLLAMA_HOST` | `http://localhost:11434` | Ollama API endpoint |

If Ollama is not running, the report is generated without the AI summary.

---

## CLI & Task Runner

### CLI (`cli.py`)

Built with [Typer](https://typer.tiangolo.com/). Key commands:

```
py-launch-lab matrix run          # Run all scenarios
py-launch-lab matrix list         # List all defined scenarios
py-launch-lab report build        # Build HTML report from JSON artifacts
py-launch-lab report build --force  # Rebuild even if up-to-date
py-launch-lab scenario run <id>   # Run a single scenario
py-launch-lab inspect exe <path>  # Inspect a PE executable
py-launch-lab probe <executable>  # Probe a binary interactively
```

The `--force` flag bypasses the freshness check (compares JSON file mtimes
against the report file).  Verbose logging is enabled automatically when
running `report build`.

### Taskfile (`taskfile.yaml`)

The project includes a [Taskfile](https://taskfile.dev/) for common operations.
The `report` task forwards the `FORCE` variable:

```yaml
report:
  cmds:
    - uv run py-launch-lab report build {{if .FORCE}}--force{{end}}
  vars:
    FORCE: '{{.FORCE | default ""}}'
```

Usage: `task report FORCE=1`

---

## Data Model (`models.py`)

The `ScenarioResult` Pydantic model is the primary evidence unit.
All fields use `model_config = ConfigDict(use_enum_values=True)` so JSON
serialisation uses string values rather than enum names.

Key enums:

- `Subsystem` — `GUI`, `CUI`, `UNKNOWN`, `NOT_PE`
- `LauncherKind` — `python`, `pythonw`, `uv`, `uvw`, `uvx`, `venv-direct`,
  `pyshim-win`, etc.

The `ProcessInfo` sub-model captures process tree snapshots with PID, name,
executable path, PE subsystem, and command line.

---

## Test Suite

75 unit tests (5 skipped on non-Windows) covering:

- PE inspection with synthetic PE files
- Matrix scenario definitions
- HTML report generation (unified table, anomaly highlighting, filter row)
- JSON schema validation
- Detection module imports
- Runner module logic
