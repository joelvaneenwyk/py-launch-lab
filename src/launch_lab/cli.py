"""
CLI entrypoint for py-launch-lab.

Commands:
    py-launch-lab setup-uv <source>       — build/resolve a custom uv binary
    py-launch-lab probe <executable>      — probe a binary (terminal detection)
    py-launch-lab scenario run <scenario-id>
    py-launch-lab matrix run
    py-launch-lab matrix list
    py-launch-lab report build [--force]
    py-launch-lab inspect exe <path>
    py-launch-lab serve                   — run matrix, build report, start local server
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Annotated

import typer
from rich.console import Console

from launch_lab import __version__
from launch_lab.uv_provider import get_custom_uv_source, get_uv_binary, setup_custom_uv

app = typer.Typer(
    name="py-launch-lab",
    help="Python Launch Lab — Windows-first Python launcher conformance tool.",
    no_args_is_help=True,
)

scenario_app = typer.Typer(help="Commands for individual scenarios.")
app.add_typer(scenario_app, name="scenario")

inspect_app = typer.Typer(help="Inspection commands.")
app.add_typer(inspect_app, name="inspect")

console = Console()


def _setup_logging(verbose: bool = True) -> None:
    """Configure logging for the CLI.

    When verbose is True, DEBUG-level messages from launch_lab are emitted
    to stderr via rich-style formatting.
    """
    level = logging.DEBUG if verbose else logging.INFO
    handler = logging.StreamHandler()
    handler.setLevel(level)
    formatter = logging.Formatter(
        fmt="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
        datefmt="%H:%M:%S",
    )
    handler.setFormatter(formatter)

    root_logger = logging.getLogger("launch_lab")
    root_logger.setLevel(level)
    # Avoid duplicate handlers on repeated calls
    if not root_logger.handlers:
        root_logger.addHandler(handler)


def _init_custom_uv(source: str) -> None:
    """Configure a custom uv binary from a path or git URL.

    Prints progress messages and exits on failure.
    """
    _setup_logging(verbose=True)
    console.print(f"[bold]Custom uv:[/bold] {source}")
    try:
        uv_bin = setup_custom_uv(source)
        console.print(f"  [green]Resolved uv binary:[/green] {uv_bin}")
    except RuntimeError as exc:
        console.print(f"  [red]Failed to resolve custom uv:[/red] {exc}")
        raise typer.Exit(1) from exc


def _run_matrix(
    output_dir: str = "artifacts/json",
    custom_uv: str | None = None,
) -> None:
    """Run the full scenario matrix and save artifacts.

    This is the shared implementation used by both ``matrix run`` and
    ``report build`` (when no JSON artifacts exist yet).
    """
    import sys as _sys

    from launch_lab.matrix import get_matrix
    from launch_lab.runner import (
        _os_version,
        _python_version,
        _uv_version,
        is_uv_available,
        provision_matrix_venv,
        run_scenario,
    )

    if custom_uv:
        _init_custom_uv(custom_uv)

    matrix = get_matrix()
    uv_available = is_uv_available()

    # Print environment info
    console.print("[bold]Environment[/bold]")
    console.print(f"  OS:     {_os_version()}")
    console.print(f"  Python: {_python_version()}")
    uv_ver = _uv_version()
    console.print(f"  uv:     {uv_ver or 'not available'}")
    uv_src = get_custom_uv_source()
    if uv_src:
        console.print(f"  uv src: [cyan]{uv_src}[/cyan]")
    console.print("")

    # Provision the matrix venv up-front so the (potentially slow)
    # venv creation + package install step is clearly visible before
    # any scenarios start running.
    has_venv_scenarios = any(s.launcher == "venv-direct" for s in matrix)
    if has_venv_scenarios:
        console.print("[bold]Provisioning matrix venv[/bold]")
        console.print(
            "  Creating a fresh venv with the active uv and installing "
            "fixture packages so entrypoint wrappers are generated …"
        )
        venv_dir = provision_matrix_venv()
        console.print(f"  [green]Venv ready:[/green] {venv_dir}")
        console.print("")

    console.print(f"[bold]Running {len(matrix)} scenarios …[/bold]")
    executed = 0
    skipped = 0
    failed: list[str] = []
    for scenario in matrix:
        if scenario.windows_only and _sys.platform != "win32":
            console.print(f"  [dim]SKIP[/dim] {scenario.scenario_id} (Windows-only)")
            skipped += 1
            continue
        if scenario.requires_uv and not uv_available:
            console.print(f"  [dim]SKIP[/dim] {scenario.scenario_id} (uv not available)")
            skipped += 1
            continue
        if scenario.skip_reason:
            console.print(f"  [dim]SKIP[/dim] {scenario.scenario_id} ({scenario.skip_reason})")
            skipped += 1
            continue
        console.print(f"  RUN  {scenario.scenario_id} … ", end="")
        result = run_scenario(
            scenario,
            save_artifact=True,
            artifact_dir=Path(output_dir),
        )
        if result.exit_code == 0:
            console.print("[green]OK[/green] (exit=0)")
        else:
            console.print(f"[red]FAIL[/red] (exit={result.exit_code})")
            failed.append(scenario.scenario_id)
            if result.stderr_text:
                for line in result.stderr_text.strip().splitlines():
                    console.print(f"        [dim]{line}[/dim]")
        executed += 1
    passed = executed - len(failed)
    console.print(
        f"\nDone: {executed} run, {passed} passed, {len(failed)} failed, {skipped} skipped."
    )
    if failed:
        console.print("\n[red]Failed scenarios:[/red]")
        for sid in failed:
            console.print(f"  • {sid}")
        raise typer.Exit(1)


@app.callback(invoke_without_command=True)
def main(
    version: bool = typer.Option(False, "--version", "-V", help="Show version and exit."),
) -> None:
    """Python Launch Lab CLI."""
    if version:
        console.print(f"py-launch-lab {__version__}")
        raise typer.Exit()


@app.command("setup-uv")
def setup_uv_cmd(
    source: str = typer.Argument(
        ...,
        help=(
            "Custom uv source: a path to a uv binary, a local Rust source "
            "directory, or a git URL (e.g. https://github.com/joelvaneenwyk/uv)."
        ),
    ),
    force: bool = typer.Option(
        False,
        "--force",
        "-f",
        help="Force a fresh build even if a cached binary already exists.",
    ),
) -> None:
    """Build or resolve a custom uv binary ahead of time.

    Run this before ``pytest`` or ``matrix run`` so that the (potentially
    slow) clone + cargo build step is clearly visible instead of making
    tests look like they hang.

    Examples:

        py-launch-lab setup-uv https://github.com/joelvaneenwyk/uv

        py-launch-lab setup-uv ./path/to/local/uv-checkout

        py-launch-lab setup-uv C:/builds/uv.exe
    """
    from launch_lab.uv_provider import resolve_cached_custom_uv

    _setup_logging(verbose=True)

    if not force:
        cached = resolve_cached_custom_uv(source)
        if cached is not None:
            console.print(f"[green]Custom uv already built:[/green] {cached}")
            _print_uv_version(cached)
            return

    console.print(f"[bold]Setting up custom uv from:[/bold] {source}")
    console.print("This may take several minutes for git sources (clone + cargo build)…")
    console.print("")
    try:
        uv_bin = setup_custom_uv(source)
    except RuntimeError as exc:
        console.print(f"\n[red]Setup failed:[/red] {exc}")
        raise typer.Exit(1) from exc

    console.print("")
    console.print(f"[green]Custom uv ready:[/green] {uv_bin}")
    _print_uv_version(uv_bin)
    console.print("")
    console.print(
        "[dim]Tip: set [bold]CUSTOM_UV[/bold] env var to this source value so "
        "that pytest and matrix-run pick it up automatically.[/dim]"
    )


def _print_uv_version(uv_bin: str) -> None:
    """Print the version of a uv binary."""
    import subprocess

    try:
        result = subprocess.run(
            [uv_bin, "--version"],
            capture_output=True,
            text=True,
            timeout=10,
        )
        if result.returncode == 0:
            console.print(f"  version: {result.stdout.strip()}")
    except (FileNotFoundError, subprocess.TimeoutExpired):
        pass


@scenario_app.command("run")
def scenario_run(
    scenario_id: str = typer.Argument(..., help="Scenario ID to run (e.g. 'python-script-py')."),
    output: str = typer.Option("artifacts/json", "--output", "-o", help="Artifact output dir."),
    custom_uv: str | None = typer.Option(
        None,
        "--custom-uv",
        help=(
            "Custom uv source: a path to a uv binary, a Rust source directory, "
            "or a git URL (e.g. https://github.com/joelvaneenwyk/uv). "
            "When set, all uv/uvx/uvw invocations use this build."
        ),
    ),
) -> None:
    """Run a single scenario by ID and save the evidence artifact."""
    from launch_lab.matrix import get_scenario
    from launch_lab.runner import run_scenario

    if custom_uv:
        _init_custom_uv(custom_uv)

    scenario = get_scenario(scenario_id)
    if scenario is None:
        console.print(f"[red]Unknown scenario:[/red] {scenario_id}")
        raise typer.Exit(1)

    console.print(f"Running scenario [bold]{scenario_id}[/bold] …")
    result = run_scenario(scenario, save_artifact=True, artifact_dir=Path(output))
    console.print(f"  exit_code          = {result.exit_code}")
    console.print(f"  pe_subsystem       = {result.pe_subsystem}")
    console.print(f"  stdout_available   = {result.stdout_available}")
    console.print(f"  stderr_available   = {result.stderr_available}")
    console.print(f"  Console Window     = {result.console_window_detected}")
    console.print(f"  Application Window = {result.visible_window_detected}")
    console.print(f"  processes          = {len(result.processes)}")
    from launch_lab.collect import artifact_filename

    console.print(f"[green]Artifact saved -> {output}/{artifact_filename(result)}[/green]")


@app.command("matrix")
def matrix_cmd(
    action: str = typer.Argument("run", help="Action: 'run' or 'list'."),
    output: str = typer.Option("artifacts/json", "--output", "-o", help="Artifact output dir."),
    custom_uv: str | None = typer.Option(
        None,
        "--custom-uv",
        help=(
            "Custom uv source: a path to a uv binary, a Rust source directory, "
            "or a git URL (e.g. https://github.com/joelvaneenwyk/uv). "
            "When set, all uv/uvx/uvw invocations use this build."
        ),
    ),
) -> None:
    """Run or list the full scenario matrix."""
    if action == "list":
        from launch_lab.matrix import get_matrix

        for scenario in get_matrix():
            console.print(f"  {scenario.scenario_id}")
    elif action == "run":
        _run_matrix(output_dir=output, custom_uv=custom_uv)
    else:
        console.print(f"[red]Unknown action:[/red] {action}")
        raise typer.Exit(1)


@app.command("report")
def report_cmd(
    action: str = typer.Argument("build", help="Action: 'build'."),
    json_dir: str = typer.Option("artifacts/json", "--json-dir", "-j", help="JSON artifacts dir."),
    output: str = typer.Option("artifacts/markdown", "--output", "-o", help="Output directory."),
    findings: str | None = typer.Option(
        None, "--findings", "-f", help="Also write report to findings directory."
    ),
    force: bool = typer.Option(
        False, "--force", help="Force regeneration even if the report is up-to-date."
    ),
    custom_uv: str | None = typer.Option(
        None,
        "--custom-uv",
        help=(
            "Custom uv source: a path to a uv binary, a Rust source directory, "
            "or a git URL (e.g. https://github.com/joelvaneenwyk/uv). "
            "When set, all uv/uvx/uvw invocations use this build."
        ),
    ),
) -> None:
    """Build reports from collected artifacts.

    If no JSON artifacts exist yet, a full matrix run is executed first
    to generate them.
    """
    _setup_logging(verbose=True)

    if custom_uv:
        _init_custom_uv(custom_uv)

    if action == "build":
        from launch_lab.collect import load_all_results
        from launch_lab.html_report import build_html_report
        from launch_lab.report import build_report

        json_path = Path(json_dir)

        # Auto-run the matrix if no JSON artifacts are present.
        results = load_all_results(json_path)
        if not results:
            console.print(
                f"[yellow]No JSON results found in[/yellow] [cyan]{json_path.resolve()}[/cyan]"
            )
            console.print("[bold]Running scenario matrix to generate artifacts …[/bold]")
            console.print("")
            _run_matrix(output_dir=str(json_path), custom_uv=custom_uv)
            console.print("")

        console.print(f"[bold]Building reports[/bold] (force={force})")
        console.print(f"  JSON source: [cyan]{json_path.resolve()}[/cyan]")

        findings_path = Path(findings) if findings else None
        dest = build_report(
            json_dir=json_path,
            output_dir=Path(output),
            findings_dir=findings_path,
        )
        if dest is None:
            console.print("[yellow]No JSON results found -- nothing to report.[/yellow]")
            raise typer.Exit(1)
        console.print(f"[green]Report written -> {dest}[/green]")
        if findings_path:
            console.print(f"[green]Findings written -> {findings_path / 'report.md'}[/green]")
        html_dest = build_html_report(json_dir=json_path, force=force)
        if html_dest is not None:
            console.print(f"[green]HTML report written -> {html_dest}[/green]")
    else:
        console.print(f"[red]Unknown action:[/red] {action}")
        raise typer.Exit(1)


@inspect_app.command("exe")
def inspect_exe(
    path: str = typer.Argument(..., help="Path to the executable to inspect."),
) -> None:
    """Inspect a Windows PE executable and print its subsystem."""
    from launch_lab.inspect_pe import inspect_pe

    result = inspect_pe(path)
    if result is None:
        console.print(f"[red]Could not inspect:[/red] {path}")
        raise typer.Exit(1)
    console.print(result)


@app.command("probe")
def probe_cmd(
    executable: str = typer.Argument(
        ..., help="Path to the executable to probe for terminal behaviour."
    ),
    extra_args: Annotated[
        list[str] | None,
        typer.Option("--arg", "-a", help="Additional argument(s) to pass in a custom test run."),
    ] = None,
) -> None:
    """Probe an executable to determine if it launches a terminal.

    Runs a sequence of diagnostic tests — PE inspection, bare execution,
    and (for Python interpreters) version / hello-world checks — then
    reports whether a console window was detected.

    Examples:

        py-launch-lab probe .cache/test_venv_0/Scripts/pythonw.exe

        py-launch-lab probe python.exe -a --version
    """
    from launch_lab.probe import probe_executable

    probe_executable(executable, console, extra_args=extra_args)


@app.command("serve")
def serve_cmd(
    json_dir: str = typer.Option("artifacts/json", "--json-dir", "-j", help="JSON artifacts dir."),
    output: str = typer.Option("artifacts", "--output", "-o", help="Output directory root."),
    port: int = typer.Option(8642, "--port", "-p", help="Port for the local HTTP server."),
    host: str = typer.Option("127.0.0.1", "--host", help="Host to bind the server to."),
    force: bool = typer.Option(
        False, "--force", help="Force re-run of matrix and report even if artifacts exist."
    ),
    skip_matrix: bool = typer.Option(
        False, "--skip-matrix", help="Skip the matrix run (use existing JSON artifacts)."
    ),
    no_browser: bool = typer.Option(
        False, "--no-browser", help="Don't automatically open a browser."
    ),
    custom_uv: str | None = typer.Option(
        None,
        "--custom-uv",
        help=(
            "Custom uv source: a path to a uv binary, a Rust source directory, "
            "or a git URL (e.g. https://github.com/joelvaneenwyk/uv). "
            "When set, all uv/uvx/uvw invocations use this build."
        ),
    ),
) -> None:
    """Run the full matrix, build reports, and start a local server to view them.

    This is the all-in-one command that:
      1. Runs the full scenario matrix (unless --skip-matrix).
      2. Builds both Markdown and HTML reports.
      3. Starts a local HTTP server serving the artifacts directory.
      4. Opens the HTML report in your default browser.

    Press Ctrl+C to stop the server.

    Examples:

        py-launch-lab serve

        py-launch-lab serve --port 9000 --no-browser

        py-launch-lab serve --skip-matrix --force
    """
    import http.server
    import os
    import socketserver
    import threading
    import time
    import webbrowser

    from launch_lab.collect import load_all_results
    from launch_lab.html_report import build_html_report
    from launch_lab.report import build_report

    _setup_logging(verbose=True)

    if custom_uv:
        _init_custom_uv(custom_uv)

    json_path = Path(json_dir)
    output_path = Path(output)
    html_output = output_path / "html"
    md_output = output_path / "markdown"

    # --- Step 1: Run the matrix ---
    if not skip_matrix:
        results = load_all_results(json_path)
        if force or not results:
            console.print("[bold cyan]Step 1/3:[/bold cyan] Running scenario matrix …")
            console.print("")
            _run_matrix(output_dir=str(json_path), custom_uv=custom_uv)
            console.print("")
        else:
            console.print(
                f"[bold cyan]Step 1/3:[/bold cyan] Using existing artifacts "
                f"({len(results)} results in {json_path})"
            )
            console.print("  [dim]Use --force to re-run the matrix.[/dim]")
            console.print("")
    else:
        console.print("[bold cyan]Step 1/3:[/bold cyan] Skipped matrix run (--skip-matrix)")
        console.print("")

    # --- Step 2: Build reports ---
    console.print("[bold cyan]Step 2/3:[/bold cyan] Building reports …")

    md_dest = build_report(
        json_dir=json_path,
        output_dir=md_output,
        findings_dir=output_path / "findings" if (output_path / "findings").exists() else None,
    )
    if md_dest:
        console.print(f"  [green]Markdown report -> {md_dest}[/green]")

    html_dest = build_html_report(json_dir=json_path, output_dir=html_output, force=force)
    if html_dest:
        console.print(f"  [green]HTML report -> {html_dest}[/green]")
    else:
        console.print("  [yellow]No results to report — run the matrix first.[/yellow]")
        raise typer.Exit(1)
    console.print("")

    # --- Step 3: Start server ---
    serve_dir = output_path.resolve()
    report_url = f"http://{host}:{port}/html/report.html"

    console.print(f"[bold cyan]Step 3/3:[/bold cyan] Starting HTTP server on {host}:{port}")
    console.print(f"  Serving: [cyan]{serve_dir}[/cyan]")
    console.print(f"  Report:  [bold green]{report_url}[/bold green]")
    console.print("")
    console.print("  Press [bold]Ctrl+C[/bold] to stop the server.")
    console.print("")

    # Open browser after a short delay to let server start
    if not no_browser:

        def _open_browser() -> None:
            time.sleep(0.5)
            webbrowser.open(report_url)

        threading.Thread(target=_open_browser, daemon=True).start()

    try:
        os.chdir(serve_dir)

        class _QuietHandler(http.server.SimpleHTTPRequestHandler):
            """Suppress request logging to keep the terminal clean."""

            def log_message(self, format: str, *args: object) -> None:  # noqa: A002
                pass

        with socketserver.TCPServer((host, port), _QuietHandler) as httpd:
            httpd.serve_forever()
    except KeyboardInterrupt:
        console.print("\n[dim]Server stopped.[/dim]")
    except OSError as exc:
        console.print(f"\n[red]Server error:[/red] {exc}")
        console.print(f"[dim]Is port {port} already in use? Try --port <number>[/dim]")
        raise typer.Exit(1) from exc
