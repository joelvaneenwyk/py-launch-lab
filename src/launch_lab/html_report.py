"""
HTML report builder for py-launch-lab.

Generates a self-contained HTML report from JSON scenario results with:
- Single unified table (no per-launcher split) with column filters
- Command line column showing relative paths
- Anomaly highlighting with expandable explanation bubbles
- Ollama AI summary integration (optional)

Verbose logging is emitted so the user can see exactly what the report
builder is doing and where it reads data from.
"""

from __future__ import annotations

import html
import json
import logging
import os
import subprocess
from datetime import UTC, datetime
from pathlib import Path

from launch_lab.collect import load_all_results
from launch_lab.expectations import Anomaly, check_expectations
from launch_lab.models import ScenarioResult

logger = logging.getLogger("launch_lab.html_report")

_DEFAULT_OUTPUT = Path("artifacts/html")


def _relative_command_line(result: ScenarioResult) -> str:
    """Build a human-friendly command line string with relative paths.

    Absolute paths that fall under the project root are converted to
    relative paths for readability (e.g. ``.venv/Scripts/pythonw.exe``).
    """
    project_root = Path(__file__).resolve().parents[2]

    parts: list[str] = []
    cmd = result.command_line or []
    if not cmd and result.resolved_executable:
        cmd = [result.resolved_executable]

    for token in cmd:
        try:
            p = Path(token)
            if p.is_absolute():
                try:
                    rel = p.resolve().relative_to(project_root.resolve())
                    parts.append(str(rel).replace("\\", "/"))
                    continue
                except ValueError:
                    pass
        except (OSError, ValueError):
            pass
        parts.append(token)
    return " ".join(parts) if parts else "N/A"


def _try_ollama_summary(
    results: list[ScenarioResult],
    anomaly_map: dict[str, list[Anomaly]],
) -> str | None:
    """Call a local Ollama instance to generate a natural-language summary.

    Returns the generated text, or None if Ollama is not available.
    """
    logger.info("Attempting to generate AI summary via Ollama …")

    # Build a compact prompt payload
    scenario_summaries = []
    for r in results:
        anomalies = anomaly_map.get(r.scenario_id, [])
        entry: dict[str, object] = {
            "scenario": r.scenario_id,
            "launcher": str(r.launcher),
            "pe_subsystem": str(r.pe_subsystem),
            "exit_code": r.exit_code,
            "console_window": r.console_window_detected,
            "visible_window": r.visible_window_detected,
            "stdout": r.stdout_available,
        }
        if anomalies:
            entry["anomalies"] = [
                {"field": a.field, "expected": a.expected, "actual": a.actual}
                for a in anomalies
            ]
        scenario_summaries.append(entry)

    total = len(results)
    n_anomalous = sum(1 for a in anomaly_map.values() if a)

    prompt = (
        "You are an expert in Windows process launch semantics and Python packaging. "
        "Below is a JSON summary of test scenario results from py-launch-lab, a tool "
        "that tests how different Python launchers (python.exe, pythonw.exe, uv, uvw, "
        "uvx, venv entry-points, pyshim-win) behave on Windows.\n\n"
        f"Total scenarios: {total}\n"
        f"Scenarios with anomalies (deviations from expected behaviour): {n_anomalous}\n\n"
        f"Results:\n```json\n{json.dumps(scenario_summaries, indent=2)}\n```\n\n"
        "Write 1-2 concise paragraphs summarising the current state of results. "
        "Focus on what is working correctly and what deviates from expectations. "
        "For anomalies, explain the likely root cause (e.g. uv creating CUI shims "
        "instead of GUI, pythonw in venvs being CUI copies, etc.) and mention any "
        "relevant upstream issues. Keep the tone technical but accessible."
    )

    model = os.environ.get("OLLAMA_MODEL", "llama3.2")
    ollama_host = os.environ.get("OLLAMA_HOST", "http://localhost:11434")

    try:
        payload = json.dumps({
            "model": model,
            "prompt": prompt,
            "stream": False,
        })
        # Use curl to avoid adding a requests dependency
        proc_result = subprocess.run(
            [
                "curl", "-s", "-X", "POST",
                f"{ollama_host}/api/generate",
                "-H", "Content-Type: application/json",
                "-d", payload,
            ],
            capture_output=True,
            text=True,
            timeout=120,
        )
        if proc_result.returncode == 0 and proc_result.stdout.strip():
            data = json.loads(proc_result.stdout)
            response_text = data.get("response", "").strip()
            if response_text:
                logger.info(
                    "Ollama summary generated successfully (%d chars).",
                    len(response_text),
                )
                return response_text
            logger.warning("Ollama returned an empty response.")
        else:
            logger.warning(
                "Ollama request failed (exit=%s): %s",
                proc_result.returncode,
                proc_result.stderr[:200] if proc_result.stderr else "no output",
            )
    except FileNotFoundError:
        logger.info("curl not found — skipping Ollama summary.")
    except subprocess.TimeoutExpired:
        logger.warning("Ollama request timed out after 120s.")
    except (json.JSONDecodeError, KeyError) as exc:
        logger.warning("Could not parse Ollama response: %s", exc)

    return None


def build_html_report(
    json_dir: Path = Path("artifacts/json"),
    output_dir: Path = _DEFAULT_OUTPUT,
    *,
    force: bool = False,
) -> Path | None:
    """
    Build a self-contained HTML report from collected JSON artifacts.

    Args:
        json_dir: Directory containing scenario JSON files.
        output_dir: Where to write the HTML report.
        force: If True, regenerate even if the report already exists and
               JSON files have not changed.

    Returns the path to the generated report, or None if no results were found.
    """
    output_dir.mkdir(parents=True, exist_ok=True)
    dest = output_dir / "report.html"

    logger.info("HTML report builder starting")
    logger.info("  JSON source dir : %s", json_dir.resolve())
    logger.info("  Output dir      : %s", output_dir.resolve())
    logger.info("  Force rebuild   : %s", force)

    # Check if rebuild is needed
    if not force and dest.exists():
        json_files = sorted(json_dir.glob("*.json"))
        if json_files:
            newest_json = max(f.stat().st_mtime for f in json_files)
            report_mtime = dest.stat().st_mtime
            if report_mtime >= newest_json:
                logger.info(
                    "Report is up-to-date (no JSON files newer than report). "
                    "Use --force to rebuild."
                )

    # Load results
    logger.info("Loading JSON artifacts from %s …", json_dir.resolve())
    results = load_all_results(json_dir)
    if not results:
        logger.warning("No JSON result files found in %s", json_dir.resolve())
        return None

    for r in results:
        src_file = json_dir / f"{r.scenario_id}.json"
        logger.info(
            "  Loaded: %-40s (exit=%s, launcher=%s, pe=%s) from %s",
            r.scenario_id,
            r.exit_code,
            r.launcher,
            r.pe_subsystem,
            src_file,
        )

    logger.info("Loaded %d scenario results.", len(results))

    # Check expectations
    anomaly_map: dict[str, list[Anomaly]] = {}
    for r in results:
        anomalies = check_expectations(r)
        anomaly_map[r.scenario_id] = anomalies
        if anomalies:
            logger.warning(
                "  ANOMALY in %s: %s",
                r.scenario_id,
                "; ".join(
                    f"{a.field}: expected={a.expected}, actual={a.actual}"
                    for a in anomalies
                ),
            )

    total_anomalies = sum(len(v) for v in anomaly_map.values())
    logger.info(
        "Expectation check complete: %d anomalies across %d scenarios.",
        total_anomalies,
        sum(1 for v in anomaly_map.values() if v),
    )

    # Try Ollama summary
    ai_summary = _try_ollama_summary(results, anomaly_map)

    # Render
    logger.info("Rendering HTML report …")
    content = _render_html_report(results, anomaly_map, ai_summary)
    dest.write_text(content, encoding="utf-8")
    logger.info("HTML report written to %s (%d bytes).", dest.resolve(), len(content))

    return dest


# -- CSS & JS ---------------------------------------------------------------

_CSS = """\
:root {
    --bg: #ffffff;
    --fg: #1a1a2e;
    --accent: #0366d6;
    --green: #22863a;
    --red: #cb2431;
    --yellow: #b08800;
    --orange: #e36209;
    --border: #e1e4e8;
    --row-alt: #f6f8fa;
    --header-bg: #24292e;
    --header-fg: #ffffff;
    --card-bg: #f6f8fa;
    --anomaly-bg: #fff8f0;
    --anomaly-border: #f9826c;
}

* { box-sizing: border-box; margin: 0; padding: 0; }

body {
    font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Helvetica, Arial, sans-serif;
    color: var(--fg);
    background: var(--bg);
    line-height: 1.6;
    max-width: 1400px;
    margin: 0 auto;
    padding: 2rem 1rem;
}

h1 { margin-bottom: 0.5rem; }
h2 {
    margin-top: 2rem; margin-bottom: 0.75rem;
    border-bottom: 1px solid var(--border); padding-bottom: 0.3rem;
}

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
.card .value { font-size: 2rem; font-weight: 700; }
.card .label { font-size: 0.85rem; color: #586069; }
.card.passed .value { color: var(--green); }
.card.failed .value { color: var(--red); }
.card.anomalies .value { color: var(--orange); }
.card.unknown .value { color: var(--yellow); }

/* AI summary */
.ai-summary {
    background: linear-gradient(135deg, #f0f7ff 0%, #f5f0ff 100%);
    border: 1px solid #c8d1e0;
    border-radius: 8px;
    padding: 1.25rem 1.5rem;
    margin-bottom: 2rem;
    font-size: 0.95rem;
    line-height: 1.7;
}
.ai-summary h3 {
    margin: 0 0 0.5rem 0;
    font-size: 1rem;
    color: #586069;
}
.ai-summary .model-tag {
    display: inline-block;
    background: #e1e4e8;
    padding: 0.1rem 0.4rem;
    border-radius: 3px;
    font-size: 0.75rem;
    font-family: monospace;
    color: #586069;
    margin-left: 0.5rem;
}

/* Table and filters */
.filter-row th {
    background: #f6f8fa;
    padding: 0.3rem 0.5rem;
}
.filter-row select, .filter-row input {
    width: 100%;
    padding: 0.25rem 0.4rem;
    border: 1px solid var(--border);
    border-radius: 4px;
    font-size: 0.8rem;
    background: white;
}

table {
    width: 100%;
    border-collapse: collapse;
    margin-bottom: 1.5rem;
    font-size: 0.85rem;
}
th {
    background: var(--header-bg);
    color: var(--header-fg);
    text-align: left;
    padding: 0.6rem 0.75rem;
    font-weight: 600;
    white-space: nowrap;
    cursor: pointer;
    user-select: none;
}
th:hover { background: #3a3f47; }
th .sort-arrow { margin-left: 4px; font-size: 0.7rem; opacity: 0.6; }

td {
    padding: 0.5rem 0.75rem;
    border-bottom: 1px solid var(--border);
}
tr:nth-child(even) { background: var(--row-alt); }
tr:hover { background: #eef2f7; }

/* Anomaly rows */
tr.anomaly-row { background: var(--anomaly-bg) !important; }
tr.anomaly-row:hover { background: #ffe8d6 !important; }
tr.anomaly-row td:first-child { border-left: 3px solid var(--anomaly-border); }

/* Anomaly detail bubble */
tr.anomaly-detail-row { background: #fff5ee; }
tr.anomaly-detail-row td {
    padding: 0;
    border-bottom: 2px solid var(--anomaly-border);
}
.anomaly-bubble {
    margin: 0.5rem 0.75rem;
    padding: 0.75rem 1rem;
    background: white;
    border: 1px solid var(--anomaly-border);
    border-left: 4px solid var(--anomaly-border);
    border-radius: 4px;
    font-size: 0.85rem;
    line-height: 1.5;
}
.anomaly-bubble strong { color: var(--red); }
.anomaly-bubble .anomaly-field {
    display: inline-block;
    background: #ffdce0;
    color: var(--red);
    padding: 0.1rem 0.4rem;
    border-radius: 3px;
    font-size: 0.8rem;
    font-weight: 600;
    margin-right: 0.5rem;
}
.anomaly-bubble .doc-link {
    display: inline-block;
    margin-top: 0.5rem;
    color: var(--accent);
    font-size: 0.8rem;
}
.anomaly-bubble .expected-vs-actual {
    margin: 0.4rem 0;
    font-family: SFMono-Regular, Consolas, 'Liberation Mono', Menlo, monospace;
    font-size: 0.8rem;
}
.anomaly-bubble .expected-vs-actual .expected { color: var(--green); }
.anomaly-bubble .expected-vs-actual .actual { color: var(--red); }

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
.badge-anomaly { background: #fff3e0; color: var(--orange); }

.launcher-tag {
    display: inline-block;
    background: #e1e4e8;
    color: #24292e;
    padding: 0.1rem 0.4rem;
    border-radius: 3px;
    font-family: SFMono-Regular, Consolas, 'Liberation Mono', Menlo, monospace;
    font-size: 0.82rem;
}

.cmd-line {
    font-family: SFMono-Regular, Consolas, 'Liberation Mono', Menlo, monospace;
    font-size: 0.8rem;
    color: #24292e;
    word-break: break-all;
    max-width: 320px;
}

.legend {
    display: flex;
    gap: 1.5rem;
    flex-wrap: wrap;
    margin-bottom: 1rem;
    font-size: 0.85rem;
    color: #586069;
}
.legend-item {
    display: flex;
    align-items: center;
    gap: 0.3rem;
}
.legend-swatch {
    display: inline-block;
    width: 14px;
    height: 14px;
    border-radius: 3px;
    border: 1px solid var(--border);
}

footer {
    margin-top: 3rem;
    padding-top: 1rem;
    border-top: 1px solid var(--border);
    color: #586069;
    font-size: 0.85rem;
}
"""

_JS = """\
document.addEventListener('DOMContentLoaded', function() {
    var table = document.getElementById('results-table');
    if (!table) return;
    var tbody = table.querySelector('tbody');
    var filterRow = table.querySelector('.filter-row');
    var headers = table.querySelectorAll('thead tr:first-child th');

    // -- Column filtering --
    var filterInputs = filterRow ? filterRow.querySelectorAll('select, input') : [];

    function applyFilters() {
        var rows = tbody.querySelectorAll('tr.data-row');
        var detailRows = tbody.querySelectorAll('tr.anomaly-detail-row');

        // Hide all detail rows first
        detailRows.forEach(function(r) { r.style.display = 'none'; });

        rows.forEach(function(row) {
            var visible = true;
            filterInputs.forEach(function(input, idx) {
                var cellText = row.children[idx]
                    ? row.children[idx].textContent.trim().toLowerCase() : '';
                var filterVal = input.value.trim().toLowerCase();
                if (!filterVal) return;
                if (input.tagName === 'SELECT') {
                    if (filterVal && cellText.indexOf(filterVal) === -1) visible = false;
                } else {
                    if (cellText.indexOf(filterVal) === -1) visible = false;
                }
            });
            row.style.display = visible ? '' : 'none';
            // Show corresponding detail row if it exists
            var detailId = row.dataset.detailRow;
            if (detailId && visible) {
                var detail = document.getElementById(detailId);
                if (detail) detail.style.display = '';
            }
        });
    }

    filterInputs.forEach(function(input) {
        input.addEventListener('change', applyFilters);
        input.addEventListener('input', applyFilters);
    });

    // -- Column sorting --
    headers.forEach(function(header, idx) {
        header.addEventListener('click', function() {
            var rows = Array.from(tbody.querySelectorAll('tr.data-row'));
            var detailMap = {};
            tbody.querySelectorAll('tr.anomaly-detail-row').forEach(function(r) {
                detailMap[r.id] = r;
            });

            var currentDir = header.dataset.sortDir || 'none';
            var newDir = currentDir === 'asc' ? 'desc' : 'asc';

            // Reset all headers
            headers.forEach(function(h) {
                h.dataset.sortDir = 'none';
                var arrow = h.querySelector('.sort-arrow');
                if (arrow) arrow.textContent = '\\u21C5';
            });
            header.dataset.sortDir = newDir;
            var arrow = header.querySelector('.sort-arrow');
            if (arrow) arrow.textContent = newDir === 'asc' ? '\\u25B2' : '\\u25BC';

            rows.sort(function(a, b) {
                var aText = a.children[idx]
                    ? a.children[idx].textContent.trim() : '';
                var bText = b.children[idx]
                    ? b.children[idx].textContent.trim() : '';
                var cmp = aText.localeCompare(bText, undefined, {numeric: true});
                return newDir === 'asc' ? cmp : -cmp;
            });

            // Re-append in order with detail rows following their parent
            rows.forEach(function(row) {
                tbody.appendChild(row);
                var detailId = row.dataset.detailRow;
                if (detailId && detailMap[detailId]) {
                    tbody.appendChild(detailMap[detailId]);
                }
            });

            applyFilters();
        });
    });
});
"""


# -- rendering helpers -------------------------------------------------------


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


def _status_badge(anomalies: list[Anomaly]) -> str:
    """Render a status badge: OK or Anomaly."""
    if not anomalies:
        return '<span class="badge badge-pass">\u2713 OK</span>'
    n = len(anomalies)
    label = f"\u26A0 {n} anomal{'y' if n == 1 else 'ies'}"
    return f'<span class="badge badge-anomaly">{label}</span>'


def _render_anomaly_bubble(anomalies: list[Anomaly]) -> str:
    """Render the expandable anomaly explanation bubble."""
    parts: list[str] = []
    parts.append('<div class="anomaly-bubble">')
    parts.append("<strong>\u26A0 Unexpected behaviour detected:</strong>")
    for a in anomalies:
        parts.append(
            f'<div style="margin-top: 0.5rem;">'
            f'<span class="anomaly-field">{_esc(a.field)}</span>'
        )
        parts.append('<div class="expected-vs-actual">')
        parts.append(f'<span class="expected">Expected: {_esc(a.expected)}</span> \u2192 ')
        parts.append(f'<span class="actual">Actual: {_esc(a.actual)}</span>')
        parts.append("</div>")
        parts.append(f"<div>{_esc(a.explanation)}</div>")
        if a.doc_url:
            parts.append(
                f'<a class="doc-link" href="{_esc(a.doc_url)}" '
                f'target="_blank">\U0001F4D6 More details \u2192</a>'
            )
        parts.append("</div>")
    parts.append("</div>")
    return "\n".join(parts)


def _collect_unique_values(
    results: list[ScenarioResult],
    anomaly_map: dict[str, list[Anomaly]],
) -> dict[str, list[str]]:
    """Collect unique values for each filterable column."""
    launchers: set[str] = set()
    platforms: set[str] = set()
    subsystems: set[str] = set()
    statuses: set[str] = set()
    console_vals: set[str] = set()
    visible_vals: set[str] = set()

    for r in results:
        launchers.add(str(r.launcher))
        platforms.add(str(r.platform))
        subsystems.add(str(r.pe_subsystem) if r.pe_subsystem else "N/A")
        anomalies = anomaly_map.get(r.scenario_id, [])
        statuses.add("\u2713 OK" if not anomalies else "\u26A0 Anomaly")
        console_vals.add(_bool_display(r.console_window_detected))
        visible_vals.add(_bool_display(r.visible_window_detected))

    return {
        "launcher": sorted(launchers),
        "platform": sorted(platforms),
        "subsystem": sorted(subsystems),
        "status": sorted(statuses),
        "console": sorted(console_vals),
        "visible": sorted(visible_vals),
    }


def _render_filter_select(options: list[str], placeholder: str = "All") -> str:
    """Render a <select> dropdown for column filtering."""
    parts = [f'<select><option value="">{_esc(placeholder)}</option>']
    for opt in options:
        parts.append(f'<option value="{_esc(opt.lower())}">{_esc(opt)}</option>')
    parts.append("</select>")
    return "".join(parts)


def _render_html_report(
    results: list[ScenarioResult],
    anomaly_map: dict[str, list[Anomaly]],
    ai_summary: str | None,
) -> str:
    """Render the complete self-contained HTML report."""
    passed = sum(1 for r in results if r.exit_code == 0)
    failed = sum(1 for r in results if r.exit_code is not None and r.exit_code != 0)
    unknown = sum(1 for r in results if r.exit_code is None)
    n_anomalous = sum(1 for v in anomaly_map.values() if v)
    platforms = sorted({r.platform for r in results})
    os_versions = sorted({r.os_version for r in results if r.os_version})
    python_versions = sorted({r.python_version for r in results})
    uv_versions = sorted({r.uv_version for r in results if r.uv_version})
    timestamp = datetime.now(tz=UTC).strftime("%Y-%m-%d %H:%M:%S UTC")
    unique_vals = _collect_unique_values(results, anomaly_map)

    parts: list[str] = []
    parts.append("<!DOCTYPE html>")
    parts.append('<html lang="en">')
    parts.append("<head>")
    parts.append('  <meta charset="utf-8">')
    parts.append('  <meta name="viewport" content="width=device-width, initial-scale=1">')
    parts.append("  <title>Python Launch Lab \u2014 Results</title>")
    parts.append(f"  <style>{_CSS}</style>")
    parts.append("</head>")
    parts.append("<body>")

    # Header
    parts.append("<h1>Python Launch Lab \u2014 Results</h1>")
    env_parts = [
        f"Generated {_esc(timestamp)}",
        f"Platforms: {_esc(', '.join(platforms))}",
    ]
    if os_versions:
        env_parts.append(f"OS: {_esc(', '.join(os_versions))}")
    if python_versions:
        env_parts.append(f"Python: {_esc(', '.join(python_versions))}")
    if uv_versions:
        env_parts.append(f"uv: {_esc(', '.join(uv_versions))}")
    parts.append(f'<p class="timestamp">{" | ".join(env_parts)}</p>')

    # Summary cards
    parts.append('<div class="summary-cards">')
    parts.append(
        f'<div class="card"><div class="value">{len(results)}</div>'
        '<div class="label">Total Scenarios</div></div>'
    )
    parts.append(
        f'<div class="card passed"><div class="value">{passed}</div>'
        '<div class="label">Passed (exit 0)</div></div>'
    )
    parts.append(
        f'<div class="card failed"><div class="value">{failed}</div>'
        '<div class="label">Failed</div></div>'
    )
    parts.append(
        f'<div class="card anomalies"><div class="value">{n_anomalous}</div>'
        '<div class="label">Anomalies</div></div>'
    )
    if unknown:
        parts.append(
            f'<div class="card unknown"><div class="value">{unknown}</div>'
            '<div class="label">Unknown</div></div>'
        )
    parts.append("</div>")

    # AI summary (if available)
    if ai_summary:
        model = os.environ.get("OLLAMA_MODEL", "llama3.2")
        parts.append('<div class="ai-summary">')
        parts.append(
            f'<h3>\U0001F916 AI Analysis '
            f'<span class="model-tag">{_esc(model)}</span></h3>'
        )
        for para in ai_summary.split("\n\n"):
            para = para.strip()
            if para:
                parts.append(f"<p>{_esc(para)}</p>")
        parts.append("</div>")

    # Legend
    parts.append('<div class="legend">')
    parts.append(
        '<div class="legend-item">'
        '<span class="legend-swatch" '
        'style="background:#dcffe4;border-color:#22863a;"></span>'
        " Matches expectations</div>"
    )
    parts.append(
        '<div class="legend-item">'
        '<span class="legend-swatch" '
        'style="background:#fff8f0;border-color:#f9826c;"></span>'
        " Anomaly \u2014 differs from expected behaviour</div>"
    )
    parts.append("</div>")

    # Single unified table
    parts.append("<h2>All Scenarios</h2>")
    parts.append('<table id="results-table">')

    columns = [
        "Scenario",
        "Status",
        "Platform",
        "Launcher",
        "Command Line",
        "Exit Code",
        "PE Subsystem",
        "Console Window",
        "Visible Window",
        "stdout",
        "stderr",
    ]
    parts.append("<thead>")
    parts.append("<tr>")
    for col in columns:
        parts.append(
            f'<th>{_esc(col)} <span class="sort-arrow">\u21C5</span></th>'
        )
    parts.append("</tr>")

    # Filter row
    parts.append('<tr class="filter-row">')
    parts.append('<th><input type="text" placeholder="Filter\u2026"></th>')
    parts.append(f"<th>{_render_filter_select(unique_vals['status'])}</th>")
    parts.append(f"<th>{_render_filter_select(unique_vals['platform'])}</th>")
    parts.append(f"<th>{_render_filter_select(unique_vals['launcher'])}</th>")
    parts.append('<th><input type="text" placeholder="Filter\u2026"></th>')
    parts.append('<th><input type="text" placeholder="Filter\u2026"></th>')
    parts.append(f"<th>{_render_filter_select(unique_vals['subsystem'])}</th>")
    parts.append(f"<th>{_render_filter_select(unique_vals['console'])}</th>")
    parts.append(f"<th>{_render_filter_select(unique_vals['visible'])}</th>")
    parts.append(f'<th>{_render_filter_select(["Yes", "No", "N/A"])}</th>')
    parts.append(f'<th>{_render_filter_select(["Yes", "No", "N/A"])}</th>')
    parts.append("</tr>")
    parts.append("</thead>")

    # Data rows
    parts.append("<tbody>")
    for i, r in enumerate(results):
        anomalies = anomaly_map.get(r.scenario_id, [])
        row_class = "data-row anomaly-row" if anomalies else "data-row"
        detail_id = f"detail-{i}" if anomalies else ""
        detail_attr = f' data-detail-row="{detail_id}"' if anomalies else ""

        cmd_line = _relative_command_line(r)

        parts.append(f'<tr class="{row_class}"{detail_attr}>')
        parts.append(f"<td>{_esc(r.scenario_id)}</td>")
        parts.append(f"<td>{_status_badge(anomalies)}</td>")
        parts.append(f"<td>{_esc(r.platform)}</td>")
        parts.append(
            f'<td><span class="launcher-tag">{_esc(r.launcher)}</span></td>'
        )
        parts.append(
            f'<td><span class="cmd-line" title="{_esc(cmd_line)}">'
            f"{_esc(cmd_line)}</span></td>"
        )
        parts.append(f"<td>{_exit_badge(r.exit_code)}</td>")
        parts.append(f"<td>{_esc(r.pe_subsystem)}</td>")
        parts.append(f"<td>{_bool_display(r.console_window_detected)}</td>")
        parts.append(f"<td>{_bool_display(r.visible_window_detected)}</td>")
        parts.append(f"<td>{_bool_display(r.stdout_available)}</td>")
        parts.append(f"<td>{_bool_display(r.stderr_available)}</td>")
        parts.append("</tr>")

        # Anomaly detail bubble row
        if anomalies:
            parts.append(
                f'<tr class="anomaly-detail-row" id="{detail_id}">'
                f'<td colspan="{len(columns)}">'
                f"{_render_anomaly_bubble(anomalies)}"
                f"</td></tr>"
            )

    parts.append("</tbody></table>")

    # Footer
    parts.append("<footer>")
    parts.append(
        f"<p>Report generated by py-launch-lab <code>html_report.py</code>"
        f" at {_esc(timestamp)}.</p>"
    )
    parts.append("</footer>")

    parts.append(f"<script>{_JS}</script>")
    parts.append("</body>")
    parts.append("</html>")

    return "\n".join(parts)
