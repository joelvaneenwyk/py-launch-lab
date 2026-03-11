"""
HTML report builder for py-launch-lab.

Generates a self-contained HTML report from JSON scenario results with
styled tables, summary statistics, and per-launcher sections.
"""

from __future__ import annotations

import html
from collections import defaultdict
from datetime import UTC, datetime
from pathlib import Path

from launch_lab.collect import load_all_results
from launch_lab.models import ScenarioResult

_DEFAULT_OUTPUT = Path("artifacts/html")


def build_html_report(
    json_dir: Path = Path("artifacts/json"),
    output_dir: Path = _DEFAULT_OUTPUT,
) -> Path | None:
    """
    Build a self-contained HTML report from collected JSON artifacts.

    Returns the path to the generated report, or None if no results were found.
    """
    results = load_all_results(json_dir)
    if not results:
        return None

    output_dir.mkdir(parents=True, exist_ok=True)
    dest = output_dir / "report.html"

    content = _render_html_report(results)
    dest.write_text(content, encoding="utf-8")

    return dest


# -- rendering helpers -------------------------------------------------------

_CSS = """\
:root {
    --bg: #ffffff;
    --fg: #1a1a2e;
    --accent: #0366d6;
    --green: #22863a;
    --red: #cb2431;
    --yellow: #b08800;
    --border: #e1e4e8;
    --row-alt: #f6f8fa;
    --header-bg: #24292e;
    --header-fg: #ffffff;
    --card-bg: #f6f8fa;
}

* { box-sizing: border-box; margin: 0; padding: 0; }

body {
    font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Helvetica, Arial, sans-serif;
    color: var(--fg);
    background: var(--bg);
    line-height: 1.6;
    max-width: 1200px;
    margin: 0 auto;
    padding: 2rem 1rem;
}

h1 { margin-bottom: 0.5rem; }
h2 {
    margin-top: 2rem; margin-bottom: 0.75rem;
    border-bottom: 1px solid var(--border); padding-bottom: 0.3rem;
}
h3 { margin-top: 1.5rem; margin-bottom: 0.5rem; }

.timestamp { color: #586069; font-size: 0.9rem; margin-bottom: 1.5rem; }

.summary-cards {
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(160px, 1fr));
    gap: 1rem;
    margin-bottom: 2rem;
}

.card {
    background: var(--card-bg);
    border: 1px solid var(--border);
    border-radius: 6px;
    padding: 1rem;
    text-align: center;
}
.card .value {
    font-size: 2rem;
    font-weight: 700;
}
.card .label {
    font-size: 0.85rem;
    color: #586069;
}
.card.passed .value { color: var(--green); }
.card.failed .value { color: var(--red); }
.card.unknown .value { color: var(--yellow); }

table {
    width: 100%;
    border-collapse: collapse;
    margin-bottom: 1.5rem;
    font-size: 0.9rem;
}
th {
    background: var(--header-bg);
    color: var(--header-fg);
    text-align: left;
    padding: 0.6rem 0.75rem;
    font-weight: 600;
}
td {
    padding: 0.5rem 0.75rem;
    border-bottom: 1px solid var(--border);
}
tr:nth-child(even) { background: var(--row-alt); }
tr:hover { background: #eef2f7; }

.badge {
    display: inline-block;
    padding: 0.15rem 0.5rem;
    border-radius: 12px;
    font-size: 0.8rem;
    font-weight: 600;
}
.badge-pass { background: #dcffe4; color: var(--green); }
.badge-fail { background: #ffdce0; color: var(--red); }
.badge-na { background: #fff3cd; color: var(--yellow); }

.launcher-tag {
    display: inline-block;
    background: #e1e4e8;
    color: #24292e;
    padding: 0.1rem 0.4rem;
    border-radius: 3px;
    font-family: SFMono-Regular, Consolas, 'Liberation Mono', Menlo, monospace;
    font-size: 0.85rem;
}

footer {
    margin-top: 3rem;
    padding-top: 1rem;
    border-top: 1px solid var(--border);
    color: #586069;
    font-size: 0.85rem;
}
"""


def _esc(value: object) -> str:
    """HTML-escape a value, showing 'N/A' for None."""
    if value is None:
        return "N/A"
    return html.escape(str(value))


def _exit_badge(exit_code: int | None) -> str:
    """Render an exit code as a colored badge."""
    if exit_code is None:
        return '<span class="badge badge-na">N/A</span>'
    if exit_code == 0:
        return '<span class="badge badge-pass">0</span>'
    return f'<span class="badge badge-fail">{html.escape(str(exit_code))}</span>'


def _bool_display(value: bool | None) -> str:
    if value is None:
        return "N/A"
    return "Yes" if value else "No"


def _render_html_report(results: list[ScenarioResult]) -> str:
    """Render a complete self-contained HTML report."""
    passed = sum(1 for r in results if r.exit_code == 0)
    failed = sum(1 for r in results if r.exit_code is not None and r.exit_code != 0)
    unknown = sum(1 for r in results if r.exit_code is None)
    platforms = sorted({r.platform for r in results})
    os_versions = sorted({r.os_version for r in results if r.os_version})
    python_versions = sorted({r.python_version for r in results})
    uv_versions = sorted({r.uv_version for r in results if r.uv_version})
    timestamp = datetime.now(tz=UTC).strftime("%Y-%m-%d %H:%M:%S UTC")

    parts: list[str] = []
    parts.append("<!DOCTYPE html>")
    parts.append('<html lang="en">')
    parts.append("<head>")
    parts.append('  <meta charset="utf-8">')
    parts.append('  <meta name="viewport" content="width=device-width, initial-scale=1">')
    parts.append("  <title>Python Launch Lab -- Results</title>")
    parts.append(f"  <style>{_CSS}</style>")
    parts.append("</head>")
    parts.append("<body>")

    # Header
    parts.append("<h1>Python Launch Lab -- Results</h1>")
    env_parts = [f"Generated {_esc(timestamp)}",
                 f"Platforms: {_esc(', '.join(platforms))}"]
    if os_versions:
        env_parts.append(f"OS: {_esc(', '.join(os_versions))}")
    if python_versions:
        env_parts.append(f"Python: {_esc(', '.join(python_versions))}")
    if uv_versions:
        env_parts.append(f"uv: {_esc(', '.join(uv_versions))}")
    parts.append(f'<p class="timestamp">{" | ".join(env_parts)}</p>')

    # Summary cards
    parts.append('<div class="summary-cards">')
    parts.append(f'<div class="card"><div class="value">{len(results)}</div>'
                 '<div class="label">Total Scenarios</div></div>')
    parts.append(f'<div class="card passed"><div class="value">{passed}</div>'
                 '<div class="label">Passed (exit 0)</div></div>')
    parts.append(f'<div class="card failed"><div class="value">{failed}</div>'
                 '<div class="label">Failed</div></div>')
    parts.append(f'<div class="card unknown"><div class="value">{unknown}</div>'
                 '<div class="label">Unknown</div></div>')
    parts.append("</div>")

    # All scenarios table
    parts.append("<h2>All Scenarios</h2>")
    parts.append("<table>")
    parts.append("<thead><tr>")
    parts.append("<th>Scenario</th><th>Platform</th><th>Launcher</th>")
    parts.append("<th>Exit Code</th><th>PE Subsystem</th>")
    parts.append("<th>Console Window</th><th>Visible Window</th>")
    parts.append("</tr></thead>")
    parts.append("<tbody>")
    for r in results:
        parts.append("<tr>")
        parts.append(f"<td>{_esc(r.scenario_id)}</td>")
        parts.append(f"<td>{_esc(r.platform)}</td>")
        parts.append(f'<td><span class="launcher-tag">{_esc(r.launcher)}</span></td>')
        parts.append(f"<td>{_exit_badge(r.exit_code)}</td>")
        parts.append(f"<td>{_esc(r.pe_subsystem)}</td>")
        parts.append(f"<td>{_bool_display(r.console_window_detected)}</td>")
        parts.append(f"<td>{_bool_display(r.visible_window_detected)}</td>")
        parts.append("</tr>")
    parts.append("</tbody></table>")

    # Per-launcher sections
    grouped: dict[str, list[ScenarioResult]] = defaultdict(list)
    for r in results:
        grouped[r.launcher].append(r)

    parts.append("<h2>Results by Launcher</h2>")
    for launcher in sorted(grouped):
        group = grouped[launcher]
        g_passed = sum(1 for r in group if r.exit_code == 0)
        g_total = len(group)
        parts.append(f'<h3><span class="launcher-tag">{_esc(launcher)}</span>'
                     f" ({g_passed}/{g_total} passed)</h3>")
        parts.append("<table>")
        parts.append("<thead><tr>")
        parts.append("<th>Scenario</th><th>Exit Code</th><th>PE Subsystem</th>")
        parts.append("<th>stdout</th><th>stderr</th>")
        parts.append("</tr></thead>")
        parts.append("<tbody>")
        for r in group:
            parts.append("<tr>")
            parts.append(f"<td>{_esc(r.scenario_id)}</td>")
            parts.append(f"<td>{_exit_badge(r.exit_code)}</td>")
            parts.append(f"<td>{_esc(r.pe_subsystem)}</td>")
            parts.append(f"<td>{_bool_display(r.stdout_available)}</td>")
            parts.append(f"<td>{_bool_display(r.stderr_available)}</td>")
            parts.append("</tr>")
        parts.append("</tbody></table>")

    # Footer
    parts.append("<footer>")
    parts.append(f"<p>Report generated by py-launch-lab <code>html_report.py</code>"
                 f" at {_esc(timestamp)}.</p>")
    parts.append("</footer>")
    parts.append("</body>")
    parts.append("</html>")

    return "\n".join(parts)
