"""
CLI entrypoint for py-launch-lab.

Commands:
    py-launch-lab scenario run <scenario-id>
    py-launch-lab matrix run
    py-launch-lab report build
    py-launch-lab inspect exe <path>
"""

from __future__ import annotations

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
) -> None:
    """Run a single scenario by ID."""
    # TODO(M2): Implement scenario execution
    console.print(f"[yellow]TODO:[/yellow] Run scenario '{scenario_id}'")
    raise typer.Exit(1)


@app.command("matrix")
def matrix_cmd(
    action: str = typer.Argument("run", help="Action: 'run' or 'list'."),
) -> None:
    """Run or list the full scenario matrix."""
    if action == "list":
        from launch_lab.matrix import get_matrix

        for scenario in get_matrix():
            console.print(f"  {scenario.scenario_id}")
    elif action == "run":
        # TODO(M2): Wire up runner
        console.print("[yellow]TODO:[/yellow] Matrix run not yet implemented.")
        raise typer.Exit(1)
    else:
        console.print(f"[red]Unknown action:[/red] {action}")
        raise typer.Exit(1)


@app.command("report")
def report_cmd(
    action: str = typer.Argument("build", help="Action: 'build'."),
    output: str = typer.Option("artifacts/markdown", "--output", "-o", help="Output directory."),
) -> None:
    """Build reports from collected artifacts."""
    if action == "build":
        # TODO(M5): Implement report generation
        console.print(f"[yellow]TODO:[/yellow] Report build → {output}")
        raise typer.Exit(1)
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
