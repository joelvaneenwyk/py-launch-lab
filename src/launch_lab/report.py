"""
Report builder for py-launch-lab.

Reads JSON artifacts and generates Markdown summary tables.

TODO(M5): Implement full report generation.
"""

from __future__ import annotations

from pathlib import Path
from typing import Optional

from launch_lab.collect import load_all_results
from launch_lab.models import ScenarioResult

_DEFAULT_OUTPUT = Path("artifacts/markdown")


def build_report(
    json_dir: Path = Path("artifacts/json"),
    output_dir: Path = _DEFAULT_OUTPUT,
) -> Optional[Path]:
    """
    Build a Markdown report from collected JSON artifacts.

    Returns the path to the generated report, or None if no results were found.

    TODO(M5): Expand into a multi-section report with per-scenario tables.
    """
    results = load_all_results(json_dir)
    if not results:
        return None

    output_dir.mkdir(parents=True, exist_ok=True)
    dest = output_dir / "report.md"

    lines = _render_report(results)
    dest.write_text("\n".join(lines), encoding="utf-8")
    return dest


def _render_report(results: list[ScenarioResult]) -> list[str]:
    """Render a simple Markdown table for the given results."""
    lines: list[str] = [
        "# Python Launch Lab — Results",
        "",
        "| Scenario | Platform | Launcher | Exit Code | PE Subsystem | Console Window |",
        "| --- | --- | --- | --- | --- | --- |",
    ]
    for r in results:
        lines.append(
            f"| {r.scenario_id} | {r.platform} | {r.launcher} "
            f"| {r.exit_code} | {r.pe_subsystem} | {r.console_window_detected} |"
        )
    lines.append("")
    return lines
