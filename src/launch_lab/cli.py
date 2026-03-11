"""
CLI entrypoint for py-launch-lab.

Commands:
    py-launch-lab scenario run <scenario-id>
    py-launch-lab matrix run
    py-launch-lab matrix list
    py-launch-lab report build
    py-launch-lab inspect exe <path>
"""

from __future__ import annotations

from pathlib import Path

import typer
from rich.console import Console

from launch_lab import __version__

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


@app.callback(invoke_without_command=True)
def main(
    version: bool = typer.Option(False, "--version", "-V", help="Show version and exit."),
) -> None:
    """Python Launch Lab CLI."""
    if version:
        console.print(f"py-launch-lab {__version__}")
        raise typer.Exit()


@scenario_app.command("run")
def scenario_run(
    scenario_id: str = typer.Argument(..., help="Scenario ID to run (e.g. 'python-script-py')."),
    output: str = typer.Option("artifacts/json", "--output", "-o", help="Artifact output dir."),
) -> None:
    """Run a single scenario by ID and save the evidence artifact."""
    from launch_lab.matrix import get_scenario
    from launch_lab.runner import run_scenario

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
    console.print(f"  console_window     = {result.console_window_detected}")
    console.print(f"  visible_window     = {result.visible_window_detected}")
    console.print(f"  processes          = {len(result.processes)}")
    console.print(f"[green]Artifact saved → {output}/{scenario_id}.json[/green]")


@app.command("matrix")
def matrix_cmd(
    action: str = typer.Argument("run", help="Action: 'run' or 'list'."),
    output: str = typer.Option("artifacts/json", "--output", "-o", help="Artifact output dir."),
) -> None:
    """Run or list the full scenario matrix."""
    if action == "list":
        from launch_lab.matrix import get_matrix

        for scenario in get_matrix():
            console.print(f"  {scenario.scenario_id}")
    elif action == "run":
        import sys as _sys

        from launch_lab.matrix import get_matrix
        from launch_lab.runner import (
            _os_version,
            _python_version,
            _uv_version,
            is_uv_available,
            run_scenario,
        )

        matrix = get_matrix()
        uv_available = is_uv_available()

        # Print environment info
        console.print("[bold]Environment[/bold]")
        console.print(f"  OS:     {_os_version()}")
        console.print(f"  Python: {_python_version()}")
        uv_ver = _uv_version()
        console.print(f"  uv:     {uv_ver or 'not available'}")
        console.print("")

        console.print(f"Running {len(matrix)} scenarios ...")
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
            result = run_scenario(scenario, save_artifact=True, artifact_dir=Path(output))
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
) -> None:
    """Build reports from collected artifacts."""
    if action == "build":
        from launch_lab.html_report import build_html_report
        from launch_lab.report import build_report

        json_path = Path(json_dir)
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
        html_dest = build_html_report(json_dir=json_path)
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
