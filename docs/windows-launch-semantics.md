# Windows Launch Semantics

## Subsystems

Every Windows executable has a **subsystem** field in its PE optional header:

| Value | Constant | Meaning |
|-------|----------|---------|
| 2 | `IMAGE_SUBSYSTEM_WINDOWS_GUI` | GUI application — no console attached by default |
| 3 | `IMAGE_SUBSYSTEM_WINDOWS_CUI` | Console application — inherits or creates a console |

`python.exe` is CUI.  `pythonw.exe` is GUI.

## uv venv pythonw.exe — CUI Trampoline

!!! warning "Unexpected: uv-venv `pythonw.exe` allocates a console"

`uv venv` does **not** copy the real GUI-subsystem `pythonw.exe` into the
virtual environment.  Instead it generates a **CUI trampoline** — a small
console-subsystem executable that internally launches the base interpreter.
Because the trampoline's PE subsystem is CUI (not GUI), Windows allocates a
console window when it is launched without an existing console.

This differs from `python -m venv`, which copies the genuine GUI-subsystem
`pythonw.exe` and therefore does **not** create a console.

| venv tool           | pythonw.exe PE subsystem | Console allocated? |
|---------------------|--------------------------|--------------------|
| `python -m venv`    | GUI                      | No                 |
| `uv venv`           | CUI (trampoline)         | **Yes**            |

This is a known `uv` behaviour (as of uv 0.10.x) and may change in future
releases.  The py-launch-lab test suite asserts the *actual* observed
behaviour rather than the expected ideal.

## Console Attachment

When a CUI executable is launched from a console, it inherits that console.
When it is launched without one (e.g. from Explorer), Windows creates a new
console window automatically.

When a GUI executable is launched, Windows does *not* attach or create a
console.  Stdout and stderr are typically unavailable.

## uv and uvw

`uv.exe` is currently a CUI executable.  When `uv run` spawns a Python
process, the subprocess inherits the console (or a new one is created).

`uvw.exe` (if present) is the GUI-subsystem counterpart.

## Creation Flags

Relevant `PROCESS_CREATION_FLAGS` for this lab:

| Flag | Value | Effect |
|------|-------|--------|
| `CREATE_NEW_CONSOLE` | 0x10 | Create a new console window for the child |
| `CREATE_NO_WINDOW` | 0x8000000 | Suppress console window for CUI child |
| `DETACHED_PROCESS` | 0x8 | Detach from parent console |

## conhost.exe

`conhost.exe` is the Windows console host.  Its presence in the process tree
is a reliable indicator that a console window exists (or existed) for a
given process, even if that window is hidden.

## Observations This Lab Makes

For each scenario, the lab records:

- PE subsystem of the top-level executable
- Whether a console window is visible (`visible_window_detected`)
- Whether `conhost.exe` appears in the process tree (`console_window_detected`)
- Stdout and stderr availability
- Exit code
