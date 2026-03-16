# Console & Window Detection Deep Dive

This document explains the low-level Windows detection techniques used by
py-launch-lab to determine whether a process creates a console window, shows
a visible window, or runs silently.

---

## Why Detection Is Hard

On Windows, console window creation is an **OS-level side effect** of
launching a CUI executable.  There is no API that says "tell me if this
process would create a console".  You have to **actually launch it** and
then **observe what happened** — in a narrow time window before the
process exits.

Key challenges:

1. **Pipes suppress consoles.**  If you redirect stdout/stderr via pipes,
   Windows satisfies the CUI process's console requirement through the
   pipe handles and does not allocate a visible console window.

2. **Fast processes vanish.**  Many processes (especially `uv tool install`,
   `uvx`, venv wrappers) exit in <100 ms.  By the time you snapshot the
   process tree, the process and its `conhost.exe` are already gone.

3. **Child processes matter.**  A GUI wrapper that spawns a CUI child will
   cause `conhost.exe` to appear under the *child*, not the parent.
   Single-level process tree queries miss this.

4. **Timing is inherently racy.**  Process tree snapshots are point-in-time.
   There is always a window between `CreateProcess` and
   `CreateToolhelp32Snapshot` where state can change.

---

## Detection Architecture

```
run_scenario()
 │
 ├── Phase 1: Window/Console Detection (Windows only)
 │    ├── Launch with CREATE_NEW_CONSOLE, no pipes
 │    ├── Poll 10× at 50ms intervals
 │    ├── If still alive:
 │    │    ├── get_process_tree()     → CreateToolhelp32Snapshot
 │    │    ├── detect_visible_window() → EnumWindows
 │    │    └── detect_console_host()   → check for conhost.exe
 │    ├── If exited early:
 │    │    └── _try_keepalive_detection()
 │    ├── _detect_child_python_subsystem()  → PE override
 │    └── Inference fallback from PE subsystem
 │
 └── Phase 2: Output Capture (all platforms)
      └── Launch with pipes, capture stdout/stderr/exit_code
```

---

## Process Tree Inspection

### CreateToolhelp32Snapshot

The core of process tree detection uses the Win32 Toolhelp API via `ctypes`:

```python
# Take a snapshot of all processes
snapshot = kernel32.CreateToolhelp32Snapshot(TH32CS_SNAPPROCESS, 0)

# Iterate through PROCESSENTRY32 structures
pe = PROCESSENTRY32()
pe.dwSize = ctypes.sizeof(pe)
kernel32.Process32First(snapshot, ctypes.byref(pe))
while True:
    if pe.th32ParentProcessID == target_pid:
        # This is a child of our target process
        children.append(ProcessInfo(
            pid=pe.th32ProcessID,
            name=pe.szExeFile.decode(),
            exe=_get_full_image_name(pe.th32ProcessID),
        ))
    if not kernel32.Process32Next(snapshot, ctypes.byref(pe)):
        break
```

### Full Image Path

Process names from `PROCESSENTRY32.szExeFile` are truncated to 260 chars
and contain only the filename (no path).  To get the full path, we use
`QueryFullProcessImageNameW`:

```python
handle = kernel32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, pid)
buf = ctypes.create_unicode_buffer(1024)
size = ctypes.wintypes.DWORD(1024)
kernel32.QueryFullProcessImageNameW(handle, 0, buf, ctypes.byref(size))
full_path = buf.value
```

### Console Host Detection

`conhost.exe` (or `WindowsTerminal.exe` / `OpenConsole.exe`) is spawned as
a child of any CUI process that creates or inherits a console.  Detection
is simple — if any child process name matches the console host set:

```python
_CONSOLE_HOST_NAMES = frozenset({
    "conhost.exe",
    "windowsterminal.exe",
    "openconsole.exe",
})

def detect_console_host(pid: int) -> bool | None:
    children = get_process_tree(pid)
    return any(child.name.lower() in _CONSOLE_HOST_NAMES for child in children)
```

### Limitation: Single-Level Tree

`get_process_tree()` only returns **direct children** of the given PID.
This means if a GUI wrapper (PID 100) spawns `pythonw.exe` (PID 200)
which gets `conhost.exe` (PID 300), querying PID 100 will NOT find
`conhost.exe`.

This is by design — recursing the entire tree is expensive and error-prone.
The child PE subsystem override compensates for this limitation.

---

## Visible Window Detection

Uses `EnumWindows` to iterate all top-level windows on the desktop:

```python
@ctypes.WINFUNCTYPE(ctypes.wintypes.BOOL, ctypes.wintypes.HWND, ctypes.wintypes.LPARAM)
def _enum_callback(hwnd, lparam):
    # Get the PID that owns this window
    pid = ctypes.wintypes.DWORD()
    user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))

    if pid.value == target_pid:
        # Check if the window is visible
        if user32.IsWindowVisible(hwnd):
            found_visible[0] = True
    return True  # continue enumeration

user32.EnumWindows(_enum_callback, 0)
```

This catches cases where a GUI process creates a visible window (e.g.
a tkinter app or message box).  For the py-launch-lab scenarios, most
processes don't create visible windows — the "visible window" is typically
the console window itself, which is detected by `detect_console_host`.

---

## The Keepalive Strategy

### The Problem

Many scenarios exit in <100 ms:

| Scenario | Typical Runtime |
|----------|----------------|
| `uv tool install` | ~50 ms (after first run) |
| `uvx --from pkg_console lab-console` | ~80 ms |
| `venv-gui-entrypoint` | ~30 ms |
| `shim-python-script-py` | ~60 ms |

By the time Phase 1 calls `get_process_tree()`, the process is already
dead and `conhost.exe` has been cleaned up.

### The Solution

```python
def _try_keepalive_detection(exe: str) -> _DetectionResult | None:
    keepalive_cmd = _build_keepalive_cmd(exe)
    if keepalive_cmd is None:
        return None

    ka_proc = subprocess.Popen(
        keepalive_cmd,
        creationflags=subprocess.CREATE_NEW_CONSOLE,
    )
    time.sleep(0.8)  # Wait for process tree to stabilise

    if ka_proc.poll() is None:
        result = _DetectionResult(
            processes=get_process_tree(ka_proc.pid),
            visible_window=detect_visible_window(ka_proc.pid),
            console_window=detect_console_host(ka_proc.pid),
            creation_flags=get_creation_flags(ka_proc.pid),
        )
        ka_proc.kill()
        return result
```

The 800 ms sleep is crucial.  Too short and `conhost.exe` hasn't been
spawned yet.  Too long and the test suite becomes slow (20 scenarios
× 800 ms = 16 seconds of keepalive overhead).

### Executable Classification

The keepalive strategy needs to know *how* to keep each executable alive:

```python
def _is_python_like(exe_path: str) -> bool:
    stem = Path(exe_path).stem.lower()
    return stem in ("python", "python3", "pythonw", "pythonw3", ...)

def _is_uv_like(exe_path: str) -> bool:
    stem = Path(exe_path).stem.lower()
    return stem in ("uv", "uvx", "uvw")

def _is_shim_like(exe_path: str) -> bool:
    stem = Path(exe_path).stem.lower()
    return stem == "pyshim-win"
```

For venv entry-point wrappers that don't match any of these, the fallback
checks for a sibling `python.exe` in the same directory.

---

## The Child PE Override

### The Problem

Consider `lab-window-gui.exe` in a uv venv:

```
lab-window-gui.exe        PE: GUI (wrapper generated by pip/uv)
  └── pythonw.exe  PE: CUI (uv trampoline — should be GUI!)
        └── conhost.exe
```

Direct detection of `lab-window-gui.exe`:
- `detect_console_host(lab_gui_pid)` → **False** (conhost is grandchild)
- `detect_application_window(lab_gui_pid)` → **True** (may have application window)
- Inference from PE → **No console** (wrapper is GUI)

But in reality, a console window **does** flash because the CUI child
allocates one.

### The Solution

```python
def _detect_child_python_subsystem(exe: str) -> str | None:
    exe_path = Path(exe)
    # Skip python/uv/shim — only check venv wrappers
    if _is_python_like(exe) or _is_uv_like(exe) or _is_shim_like(exe):
        return None
    # Check for sibling python.exe
    sibling_python = exe_path.parent / "python.exe"
    if not sibling_python.exists():
        return None
    # GUI wrapper → check pythonw.exe PE
    wrapper_pe = inspect_pe(str(exe_path))
    if wrapper_pe == "GUI":
        pythonw = exe_path.parent / "pythonw.exe"
        if pythonw.exists():
            return inspect_pe(str(pythonw))
    # CUI wrapper → check python.exe PE
    return inspect_pe(str(sibling_python))
```

The override in `run_scenario()`:

```python
child_sub = _detect_child_python_subsystem(cmd[0])
if child_sub is not None:
    effective_subsystem = child_sub
    # Critical: GUI wrapper + CUI child = console WILL appear
    if pe_subsystem == "GUI" and child_sub == "CUI":
        console_window = True
```

This is **deterministic** — it doesn't depend on timing.  If the child
Python binary is CUI, a console will always be allocated, period.

This behaviour is caused by [astral-sh/uv#9781](https://github.com/astral-sh/uv/issues/9781)
and is being investigated at [joelvaneenwyk/uv#1](https://github.com/joelvaneenwyk/uv/issues/1)
with a fix PR at [joelvaneenwyk/uv#2](https://github.com/joelvaneenwyk/uv/pull/2).

---

## Creation Flags

The following `PROCESS_CREATION_FLAGS` are relevant:

| Flag | Value | Effect |
|------|-------|--------|
| `CREATE_NEW_CONSOLE` | `0x00000010` | Force a new console window |
| `CREATE_NO_WINDOW` | `0x08000000` | Suppress console for CUI child |
| `DETACHED_PROCESS` | `0x00000008` | Detach from parent's console |

Phase 1 uses `CREATE_NEW_CONSOLE` to ensure the process gets its own
console (rather than inheriting the test runner's console), making
`conhost.exe` detection unambiguous.

The Rust shim (`pyshim-win`) uses `CREATE_NO_WINDOW` when spawning
child processes, which is why shim scenarios show `console_window = False`
even when the child is `python.exe` (CUI).

---

## Reliability Assessment

| Detection Method | Reliability | Notes |
|-----------------|------------|-------|
| PE subsystem inspection | **Very High** | Reads file on disk; deterministic |
| conhost.exe detection | **Medium** | Depends on timing; misses grandchildren |
| Visible window detection | **Medium** | Depends on timing; EnumWindows is racy |
| Keepalive detection | **High** | Reliable but adds ~800 ms per scenario |
| Child PE override | **Very High** | Deterministic file inspection |
| Inference fallback | **High** | Based on PE subsystem; correct by definition |

The combination of all methods produces reliable results for all 20 scenarios.
