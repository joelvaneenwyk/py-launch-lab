"""
Probe an arbitrary executable to determine its terminal/console behaviour.

Runs a battery of diagnostic tests and reports whether the executable
allocates a Console Window, creates an Application Window, etc.  This is
useful for verifying that detection logic works correctly for any given
binary.
"""

from __future__ import annotations

import shutil
import subprocess
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path

from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

from launch_lab.detect_windows import (
    detect_console_host,
    detect_visible_window,
    get_process_tree,
)
from launch_lab.inspect_pe import inspect_pe
from launch_lab.models import ProcessInfo, Subsystem

_IS_WINDOWS = sys.platform == "win32"


# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------


@dataclass
class ProbeTest:
    """Result of a single probe test."""

    label: str
    command: list[str]
    exit_code: int | None = None
    stdout_text: str | None = None
    stderr_text: str | None = None
    console_window: bool | None = None
    visible_window: bool | None = None
    processes: list[ProcessInfo] = field(default_factory=list)
    error: str | None = None
    output_captured: bool = True  # False when launched without pipes (detached mode)


@dataclass
class ProbeReport:
    """Full probe report for an executable."""

    exe_path: str
    resolved_path: str | None
    pe_subsystem: Subsystem | None
    tests: list[ProbeTest] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Core probe logic
# ---------------------------------------------------------------------------


def _make_keepalive_cmd(exe: str) -> list[str] | None:
    """Return a command that keeps *exe* alive long enough for window detection.

    For Python-like executables we use ``-c "import time; time.sleep(10)"``.
    Returns ``None`` if no keepalive strategy is known for the executable.
    """
    if _is_python_like(exe):
        return [exe, "-c", "import time; time.sleep(10)"]
    return None


def _detect_windows_for_cmd(
    cmd: list[str],
    result: ProbeTest,
) -> None:
    """Phase 1 — Window/console detection on Windows.

    Launches *cmd* with ``CREATE_NEW_CONSOLE`` and probes for application windows
    and console-host processes.  If the process exits before detection can run
    (common for fast commands like ``python --version``), a *keepalive* fallback
    is launched so we can still observe the console/window behaviour — which
    depends on the PE subsystem, not the command-line arguments.
    """
    detect_proc = subprocess.Popen(
        cmd,
        creationflags=subprocess.CREATE_NEW_CONSOLE,
        # No stdout/stderr pipes — the process gets its own console.
    )

    # Poll aggressively: check every 50 ms for up to ~300 ms.
    for _ in range(6):
        time.sleep(0.05)
        if detect_proc.poll() is not None:
            break  # exited before we could detect
    else:
        # Process still running after the loop — sleep a bit more for stability.
        time.sleep(0.2)

    if detect_proc.poll() is None:
        # Process is still alive — observe windows now.
        result.processes = get_process_tree(detect_proc.pid)
        result.visible_window = detect_visible_window(detect_proc.pid)
        result.console_window = detect_console_host(detect_proc.pid)
        detect_proc.kill()
        detect_proc.wait()
        return

    detect_proc.wait()

    # Process exited too quickly — console host and windows are already gone.
    # Re-launch with a keepalive command so we can still observe the
    # console/window behaviour (which depends on the EXE, not the args).
    keepalive = _make_keepalive_cmd(cmd[0])
    if keepalive is None:
        return  # No keepalive strategy available for this executable.

    ka_proc = subprocess.Popen(
        keepalive,
        creationflags=subprocess.CREATE_NEW_CONSOLE,
    )
    time.sleep(0.5)
    if ka_proc.poll() is None:
        result.processes = get_process_tree(ka_proc.pid)
        result.visible_window = detect_visible_window(ka_proc.pid)
        result.console_window = detect_console_host(ka_proc.pid)
        ka_proc.kill()
    ka_proc.wait()


def _run_single_test(
    cmd: list[str],
    label: str,
    timeout: float = 10.0,
    *,
    capture_output: bool = True,
) -> ProbeTest:
    """Run a single probe test and collect observations.

    On Windows a *window-detection pass* is always performed first: the command
    is launched with ``CREATE_NEW_CONSOLE`` and without pipes so that Windows
    allocates a real console (exactly like Win+R).  When pipes are attached,
    Windows suppresses new console allocation, so application-window detection
    would always return ``False`` — this pass avoids that.

    When *capture_output* is ``True`` a second *piped pass* is then run to
    collect stdout, stderr, and the real exit code.  Set *capture_output* to
    ``False`` for tests where output is not meaningful (e.g. bare execution).
    """
    result = ProbeTest(label=label, command=cmd, output_captured=capture_output)

    try:
        # --------------------------------------------------------------------
        # Phase 1 — Window detection (Windows only, always)
        # Launch with CREATE_NEW_CONSOLE so Windows allocates a real console.
        # Without this, redirected pipes suppress console allocation and
        # application-window detection would always report False for CUI executables.
        # --------------------------------------------------------------------
        if _IS_WINDOWS:
            _detect_windows_for_cmd(cmd, result)

        # --------------------------------------------------------------------
        # Phase 2 — Output capture (optional)
        # Run again with pipes to collect stdout/stderr and the real exit code.
        # --------------------------------------------------------------------
        if capture_output:
            cap_proc = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
            )
            try:
                out, err = cap_proc.communicate(timeout=timeout)
            except subprocess.TimeoutExpired:
                cap_proc.kill()
                out, err = cap_proc.communicate()

            result.exit_code = cap_proc.returncode
            result.stdout_text = out.strip() if out and out.strip() else None
            result.stderr_text = err.strip() if err and err.strip() else None

    except FileNotFoundError:
        result.error = f"Executable not found: {cmd[0]}"
    except PermissionError:
        result.error = f"Permission denied: {cmd[0]}"
    except (OSError, subprocess.SubprocessError) as exc:
        result.error = f"{type(exc).__name__}: {exc}"

    return result


def _is_python_like(exe_path: str) -> bool:
    """Heuristically check if the executable looks like a Python interpreter."""
    stem = Path(exe_path).stem.lower()
    return stem in (
        "python",
        "python3",
        "pythonw",
        "pythonw3",
    ) or stem.startswith(("python3.", "pythonw3."))


def probe_executable(
    exe_path: str,
    console: Console,
    *,
    extra_args: list[str] | None = None,
) -> ProbeReport:
    """Run diagnostic probes on an executable and display results.

    Tests executed:
    1. Static PE header inspection.
    2. Bare execution (no arguments).
    3. If Python-like: ``--version``, ``-c "print('hello')"``.
    4. If *extra_args* are given, an additional run with those args.

    Returns the :class:`ProbeReport` for programmatic use.
    """
    path_obj = Path(exe_path)
    resolved: str | None
    if path_obj.exists():
        resolved = str(path_obj.resolve())
    else:
        # Try PATH lookup for bare command names like "python.exe"
        which_result = shutil.which(exe_path)
        resolved = str(Path(which_result).resolve()) if which_result else None
    target = resolved or exe_path

    # -- Static PE inspection -----------------------------------------------
    pe_sub = inspect_pe(target) if resolved else None
    report = ProbeReport(
        exe_path=exe_path,
        resolved_path=resolved,
        pe_subsystem=pe_sub,
    )

    console.print()
    console.print(
        Panel(
            f"[bold]{exe_path}[/bold]\nResolved: {resolved or '[red]not found[/red]'}",
            title="Probing executable",
            expand=False,
        )
    )

    # -- 1. PE subsystem ----------------------------------------------------
    _print_pe_summary(pe_sub, console)

    if resolved is None:
        console.print("[red]Cannot run tests — executable not found.[/red]")
        return report

    # -- 2. Bare execution --------------------------------------------------
    console.print()
    console.rule("[bold]Test: bare execution (no arguments)[/bold]")
    bare = _run_single_test([target], "bare execution", capture_output=False)
    report.tests.append(bare)
    _print_test(bare, console)

    # -- 3. Python-specific tests -------------------------------------------
    is_py = _is_python_like(exe_path)
    if is_py:
        console.print()
        console.rule("[bold]Test: --version[/bold]")
        ver = _run_single_test([target, "--version"], "--version")
        report.tests.append(ver)
        _print_test(ver, console)

        console.print()
        console.rule("[bold]Test: -c \"print('hello')\"[/bold]")
        hello = _run_single_test(
            [target, "-c", "print('hello')"],
            "-c print('hello')",
        )
        report.tests.append(hello)
        _print_test(hello, console)

        console.print()
        console.rule('[bold]Test: -c "import sys; print(sys.executable)"[/bold]')
        sysexe = _run_single_test(
            [target, "-c", "import sys; print(sys.executable)"],
            "-c sys.executable",
        )
        report.tests.append(sysexe)
        _print_test(sysexe, console)

    # -- 4. Extra args (user-supplied) --------------------------------------
    if extra_args:
        label = " ".join(extra_args)
        console.print()
        console.rule(f"[bold]Test: {label}[/bold]")
        custom = _run_single_test([target, *extra_args], label)
        report.tests.append(custom)
        _print_test(custom, console)

    # -- Summary ------------------------------------------------------------
    _print_summary(report, console)

    return report


# ---------------------------------------------------------------------------
# Rich output helpers
# ---------------------------------------------------------------------------


def _subsystem_label(sub: Subsystem | None) -> str:
    if sub is None:
        return "N/A"
    labels = {
        Subsystem.GUI: "GUI  (IMAGE_SUBSYSTEM_WINDOWS_GUI — no console allocated)",
        Subsystem.CUI: "CUI  (IMAGE_SUBSYSTEM_WINDOWS_CUI — console allocated)",
        Subsystem.NOT_PE: "Not a PE file",
        Subsystem.UNKNOWN: "Unknown subsystem",
    }
    return labels.get(sub, str(sub))


def _bool_indicator(val: bool | None) -> str:
    if val is None:
        return "[dim]n/a[/dim]"
    return "[green]Yes[/green]" if val else "[red]No[/red]"


def _print_pe_summary(pe_sub: Subsystem | None, console: Console) -> None:
    console.print()
    console.rule("[bold]PE Header Inspection[/bold]")
    console.print(f"  Subsystem: {_subsystem_label(pe_sub)}")

    if pe_sub == Subsystem.GUI:
        console.print(
            "  [dim]→ This is a GUI executable.  Windows will [bold]not[/bold] "
            "automatically allocate a console.[/dim]"
        )
    elif pe_sub == Subsystem.CUI:
        console.print(
            "  [dim]→ This is a console executable.  Windows [bold]will[/bold] "
            "allocate a console window if one is not already attached.[/dim]"
        )


def _print_test(test: ProbeTest, console: Console) -> None:
    if test.error:
        console.print(f"  [red]Error:[/red] {test.error}")
        return

    table = Table(show_header=False, box=None, padding=(0, 2))
    table.add_column("Key", style="bold")
    table.add_column("Value")

    table.add_row("Exit code", str(test.exit_code))
    table.add_row("Console Window", _bool_indicator(test.console_window))
    table.add_row("Application Window", _bool_indicator(test.visible_window))
    table.add_row(
        "Process tree",
        ", ".join(p.exe or p.name for p in test.processes)
        if test.processes
        else "[dim](empty)[/dim]",
    )

    if not test.output_captured:
        table.add_row("Stdout", "[dim](not captured -- launched without pipes)[/dim]")
        table.add_row("Stderr", "[dim](not captured -- launched without pipes)[/dim]")
    else:
        if test.stdout_text:
            # Truncate long output
            out = test.stdout_text
            if len(out) > 200:
                out = out[:200] + " ..."
            table.add_row("Stdout", out)
        else:
            table.add_row("Stdout", "[dim](empty)[/dim]")

        if test.stderr_text:
            err = test.stderr_text
            if len(err) > 200:
                err = err[:200] + " ..."
            table.add_row("Stderr", err)

    console.print(table)


def _print_summary(report: ProbeReport, console: Console) -> None:
    console.print()

    # Determine overall verdict
    launches_terminal = False
    reason_parts: list[str] = []

    if report.pe_subsystem == Subsystem.CUI:
        launches_terminal = True
        reason_parts.append("PE subsystem is CUI (console)")

    # Check runtime observations
    any_console = any(t.console_window for t in report.tests if t.console_window is not None)
    any_visible = any(t.visible_window for t in report.tests if t.visible_window is not None)

    if any_console:
        launches_terminal = True
        reason_parts.append("console host (conhost.exe / Windows Terminal) detected")

    if any_visible:
        reason_parts.append("application window detected")

    if report.pe_subsystem == Subsystem.GUI and not any_console:
        reason_parts.append("PE subsystem is GUI — no console allocated")

    lines = Text()
    if launches_terminal:
        lines.append("VERDICT: ", style="bold")
        lines.append("LAUNCHES TERMINAL", style="bold red")
        lines.append("\n")
    else:
        lines.append("VERDICT: ", style="bold")
        lines.append("DOES NOT LAUNCH TERMINAL", style="bold green")
        lines.append("\n")

    for part in reason_parts:
        bullet = "  • " + part + "\n"
        lines.append(bullet)

    console.print(Panel(lines, title="Summary", expand=False))
