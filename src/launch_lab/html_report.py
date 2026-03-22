"""
HTML report builder for py-launch-lab.

Generates a self-contained HTML report from JSON scenario results with:
- Single unified table (no per-launcher split) with column filters
- Command line column showing relative paths
- Anomaly highlighting with expandable explanation bubbles
- AI summary integration: GitHub Models API (in CI) or Ollama (locally)

Verbose logging is emitted so the user can see exactly what the report
builder is doing and where it reads data from.
"""

from __future__ import annotations

import html
import json
import logging
import os
import urllib.error
import urllib.request
from datetime import UTC, datetime
from pathlib import Path

from launch_lab.collect import artifact_filename, load_all_results
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


def _build_ai_prompt(
    results: list[ScenarioResult],
    anomaly_map: dict[str, list[Anomaly]],
) -> str:
    """Build the AI prompt payload shared by all inference providers."""
    scenario_summaries = []
    for r in results:
        anomalies = anomaly_map.get(_result_key(r), [])
        entry: dict[str, object] = {
            "scenario": r.scenario_id,
            "uv_version": r.uv_version,
            "launcher": str(r.launcher),
            "pe_subsystem": str(r.pe_subsystem),
            "exit_code": r.exit_code,
            "console_window": r.console_window_detected,
            "visible_window": r.visible_window_detected,
            "stdout": r.stdout_available,
        }
        if anomalies:
            entry["anomalies"] = [
                {"field": a.field, "expected": a.expected, "actual": a.actual} for a in anomalies
            ]
        scenario_summaries.append(entry)

    total = len(results)
    n_anomalous = sum(1 for v in anomaly_map.values() if v)
    uv_versions = sorted({r.uv_version for r in results if r.uv_version})

    version_note = ""
    if len(uv_versions) > 1:
        version_note = (
            f"Results span multiple uv versions: {', '.join(uv_versions)}. "
            "Compare anomaly patterns across versions to identify regressions or fixes.\n\n"
        )

    return (
        "You are an expert in Windows process launch semantics and Python packaging. "
        "Below is a JSON summary of test scenario results from py-launch-lab, a tool "
        "that tests how different Python launchers (python.exe, pythonw.exe, uv, uvw, "
        "uvx, venv entry-points, pyshim-win) behave on Windows.\n\n"
        f"Total scenarios: {total}\n"
        f"Scenarios with anomalies (deviations from expected behaviour): {n_anomalous}\n\n"
        f"{version_note}"
        "IMPORTANT CONTEXT — Source builds:\n"
        "When results include multiple uv builds, one is the official astral-sh/uv "
        "release and others are custom builds from the joelvaneenwyk/uv fork that "
        "include fixes from these pull requests:\n"
        "• PR #2 (joelvaneenwyk/uv): 'Fix Windows pythonw.exe venv launcher using "
        "console instead of GUI subsystem' — fixed the PE subsystem of the venv "
        "pythonw.exe wrapper from CUI to GUI so it no longer allocates a console "
        "window on launch.\n"
        "• PR #3 (joelvaneenwyk/uv): 'Fix GUI script console window: use "
        "CREATE_NO_WINDOW in trampoline for GUI launchers' — updated the Rust "
        "trampoline used for GUI-subsystem entry-point scripts so that child "
        "processes are spawned with CREATE_NO_WINDOW, preventing a console flash "
        "even when the trampoline itself is a GUI executable.\n\n"
        "When comparing builds, identify which anomalies are fixed in the custom "
        "fork and which remain in the official release.\n\n"
        f"Results:\n```json\n{json.dumps(scenario_summaries, indent=2)}\n```\n\n"
        "Write 1-2 concise paragraphs summarising the current state of results. "
        "Focus on what is working correctly and what deviates from expectations. "
        "For anomalies, explain the likely root cause (e.g. uv creating CUI shims "
        "instead of GUI, pythonw in venvs being CUI copies, etc.) and mention any "
        "relevant upstream issues. Clearly state which build (official or custom "
        "fork) succeeded and which had failures, and why. Keep the tone technical "
        "but accessible."
    )


def _try_github_models_summary(
    results: list[ScenarioResult],
    anomaly_map: dict[str, list[Anomaly]],
) -> str | None:
    """Generate an AI summary using the GitHub Models API.

    Used automatically when running inside GitHub Actions (``GITHUB_ACTIONS``
    environment variable is set).  Requires ``GITHUB_TOKEN`` to be available.
    Returns the generated text, or None if unavailable or on error.
    """
    token = os.environ.get("GITHUB_TOKEN", "")
    if not token:
        logger.info("GITHUB_TOKEN not set -- skipping GitHub Models summary.")
        return None

    logger.info("Attempting to generate AI summary via GitHub Models API ...")

    prompt = _build_ai_prompt(results, anomaly_map)
    model = os.environ.get("GITHUB_MODELS_MODEL", "gpt-4o")

    payload = json.dumps({
        "model": model,
        "messages": [{"role": "user", "content": prompt}],
    }).encode()

    req = urllib.request.Request(
        "https://models.inference.ai.azure.com/chat/completions",
        data=payload,
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {token}",
        },
        method="POST",
    )

    try:
        with urllib.request.urlopen(req, timeout=120) as resp:
            data = json.loads(resp.read().decode())
            response_text = data["choices"][0]["message"]["content"].strip()
            if response_text:
                logger.info(
                    "GitHub Models summary generated successfully (%d chars).",
                    len(response_text),
                )
                return response_text
            logger.warning("GitHub Models API returned an empty response.")
    except urllib.error.URLError as exc:
        logger.warning("GitHub Models API request failed: %s", exc)
    except (json.JSONDecodeError, KeyError, IndexError) as exc:
        logger.warning("Could not parse GitHub Models API response: %s", exc)
    except TimeoutError:
        logger.warning("GitHub Models API request timed out.")

    return None


def _try_ollama_summary(
    results: list[ScenarioResult],
    anomaly_map: dict[str, list[Anomaly]],
) -> str | None:
    """Call a local Ollama instance to generate a natural-language summary.

    Returns the generated text, or None if Ollama is not available.
    """
    import subprocess

    logger.info("Attempting to generate AI summary via Ollama ...")

    prompt = _build_ai_prompt(results, anomaly_map)

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
                "curl",
                "-s",
                "-X",
                "POST",
                f"{ollama_host}/api/generate",
                "-H",
                "Content-Type: application/json",
                "-d",
                payload,
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
        logger.info("curl not found -- skipping Ollama summary.")
    except subprocess.TimeoutExpired:
        logger.warning("Ollama request timed out after 120s.")
    except (json.JSONDecodeError, KeyError) as exc:
        logger.warning("Could not parse Ollama response: %s", exc)

    return None


def _try_ai_summary(
    results: list[ScenarioResult],
    anomaly_map: dict[str, list[Anomaly]],
) -> tuple[str | None, str]:
    """Try to generate an AI summary using the best available provider.

    In GitHub Actions (``GITHUB_ACTIONS`` env var set), the GitHub Models
    API is used.  Otherwise, falls back to a local Ollama instance.

    Returns a ``(text, provider)`` tuple where *provider* is one of
    ``"github-models"``, ``"ollama"``, or ``""`` (no summary generated).
    """
    if os.environ.get("GITHUB_ACTIONS"):
        text = _try_github_models_summary(results, anomaly_map)
        if text is not None:
            return text, "github-models"
        # Fall through to Ollama in case token isn't available
    text = _try_ollama_summary(results, anomaly_map)
    return (text, "ollama") if text is not None else (None, "")


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

    # Sort results by uv version then scenario id so that rows from the same
    # uv build are grouped together in the report.
    results.sort(key=lambda r: (r.uv_version or "", r.scenario_id))

    for r in results:
        src_file = json_dir / artifact_filename(r)
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
        anomaly_map[_result_key(r)] = anomalies
        if anomalies:
            logger.warning(
                "  ANOMALY in %s: %s",
                r.scenario_id,
                "; ".join(
                    f"{a.field}: expected={a.expected}, actual={a.actual}" for a in anomalies
                ),
            )

    total_anomalies = sum(len(v) for v in anomaly_map.values())
    logger.info(
        "Expectation check complete: %d anomalies across %d scenarios.",
        total_anomalies,
        sum(1 for v in anomaly_map.values() if v),
    )

    # Try AI summary (GitHub Models in CI, Ollama locally)
    ai_summary, ai_provider = _try_ai_summary(results, anomaly_map)

    # Render
    logger.info("Rendering HTML report ...")
    content = _render_html_report(results, anomaly_map, ai_summary, ai_provider)
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

ul, ol {
    margin: 1rem 0;
    padding-left: 2rem;
}
li {
    margin: 0.5rem 0;
    line-height: 1.7;
}

/* Issue diagnosis section */
.issue-diagnosis {
    background: #f8f9fa;
    border: 1px solid var(--border);
    border-radius: 8px;
    padding: 1.25rem 1.5rem;
    margin-bottom: 1.5rem;
}
.issue-diagnosis h3 {
    margin: 0 0 0.75rem 0;
    font-size: 1.05rem;
}
.issue-diagnosis a {
    color: var(--accent);
    text-decoration: none;
}
.issue-diagnosis a:hover {
    text-decoration: underline;
}
.issue-diagnosis code {
    background: #e8edf3;
    padding: 0.1rem 0.35rem;
    border-radius: 3px;
    font-size: 0.88rem;
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
th[title] { position: relative; }
th[title]:hover::after {
    content: attr(title);
    position: absolute;
    top: 100%;
    left: 50%;
    transform: translateX(-50%);
    background: #1b1f23;
    color: #e1e4e8;
    padding: 6px 10px;
    border-radius: 4px;
    font-size: 0.78rem;
    font-weight: 400;
    white-space: normal;
    width: max-content;
    max-width: 280px;
    z-index: 100;
    box-shadow: 0 2px 8px rgba(0,0,0,0.3);
    pointer-events: none;
}

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

/* uv versions summary table */
.uv-versions-table {
    width: auto;
    margin-bottom: 1.5rem;
    border-collapse: collapse;
    font-size: 0.9rem;
}
.uv-versions-table th {
    background: #2d333b;
    color: var(--header-fg);
    text-align: left;
    padding: 0.5rem 1rem;
    font-weight: 600;
    cursor: default;
}
.uv-versions-table th:hover { background: #3a3f47; }
.uv-versions-table td {
    padding: 0.5rem 1rem;
    border-bottom: 1px solid var(--border);
}
.uv-versions-table tr:nth-child(even) { background: var(--row-alt); }
.uv-versions-table tr:hover { background: #eef2f7; }

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


def _result_key(r: ScenarioResult) -> str:
    """Return a unique key for *r* suitable for use as a dict key.

    When the result carries a ``uv_version_hash`` the key is
    ``<scenario_id>__<hash>`` so that results from different uv builds
    never collide.  Falls back to ``scenario_id`` alone for legacy results
    that predate the versioned artifact naming scheme.
    """
    if r.uv_version_hash:
        return f"{r.scenario_id}__{r.uv_version_hash}"
    return r.scenario_id


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
    label = f"\u26a0 {n} anomal{'y' if n == 1 else 'ies'}"
    return f'<span class="badge badge-anomaly">{label}</span>'


def _render_anomaly_bubble(anomalies: list[Anomaly]) -> str:
    """Render the expandable anomaly explanation bubble."""
    parts: list[str] = []
    parts.append('<div class="anomaly-bubble">')
    parts.append("<strong>\u26a0 Unexpected behaviour detected:</strong>")
    for a in anomalies:
        parts.append(
            f'<div style="margin-top: 0.5rem;"><span class="anomaly-field">{_esc(a.field)}</span>'
        )
        parts.append('<div class="expected-vs-actual">')
        parts.append(f'<span class="expected">Expected: {_esc(a.expected)}</span> \u2192 ')
        parts.append(f'<span class="actual">Actual: {_esc(a.actual)}</span>')
        parts.append("</div>")
        parts.append(f"<div>{_esc(a.explanation)}</div>")
        if a.doc_url:
            parts.append(
                f'<a class="doc-link" href="{_esc(a.doc_url)}" '
                f'target="_blank">\U0001f4d6 More details \u2192</a>'
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
    uv_versions: set[str] = set()
    subsystems: set[str] = set()
    statuses: set[str] = set()
    console_vals: set[str] = set()
    app_window_vals: set[str] = set()

    for r in results:
        launchers.add(str(r.launcher))
        platforms.add(str(r.platform))
        uv_versions.add(str(r.uv_version) if r.uv_version else "N/A")
        subsystems.add(str(r.pe_subsystem) if r.pe_subsystem else "N/A")
        anomalies = anomaly_map.get(_result_key(r), [])
        statuses.add("\u2713 OK" if not anomalies else "\u26a0 Anomaly")
        console_vals.add(_bool_display(r.console_window_detected))
        app_window_vals.add(_bool_display(r.visible_window_detected))

    return {
        "launcher": sorted(launchers),
        "platform": sorted(platforms),
        "uv_version": sorted(uv_versions),
        "subsystem": sorted(subsystems),
        "status": sorted(statuses),
        "console": sorted(console_vals),
        "app_window": sorted(app_window_vals),
    }


def _render_filter_select(options: list[str], placeholder: str = "All") -> str:
    """Render a <select> dropdown for column filtering."""
    parts = [f'<select><option value="">{_esc(placeholder)}</option>']
    for opt in options:
        parts.append(f'<option value="{_esc(opt.lower())}">{_esc(opt)}</option>')
    parts.append("</select>")
    return "".join(parts)


def _render_uv_versions_table(results: list[ScenarioResult]) -> str:
    """Render a summary table of uv versions tested and their sources.

    Groups results by ``uv_version`` and ``uv_version_hash`` to identify
    distinct builds.  For each build, infers whether it is the official
    Astral release or a custom fork build based on the version hash presence
    and the number of distinct builds.
    """
    # Collect unique (version, hash) pairs and count scenarios for each
    version_info: dict[tuple[str, str | None], int] = {}
    for r in results:
        key = (r.uv_version or "N/A", r.uv_version_hash)
        version_info[key] = version_info.get(key, 0) + 1

    if not version_info:
        return "<p><em>No uv version information available.</em></p>"

    sorted_versions = sorted(version_info.keys(), key=lambda k: (k[0], k[1] or ""))

    # Infer source labels: if there is more than one distinct hash for
    # versions that look similar, the first is likely official and
    # additional ones are custom builds.
    seen_version_strings: dict[str, int] = {}
    for ver, _hash in sorted_versions:
        seen_version_strings[ver] = seen_version_strings.get(ver, 0) + 1

    # Check whether any build carries a '+' custom marker.
    any_custom_marker = any("+" in ver for ver, _hash in sorted_versions)

    def _infer_source(
        ver: str,
        ver_hash: str | None,
        occurrence: int,
        idx: int,
        has_multiple: bool,
    ) -> str:
        """Infer whether a build is the official release or a custom fork.

        Uses the ``+`` marker in the version string (e.g. ``0.7.12+dev``)
        as a reliable indicator of a custom build.  When no marker is
        present and there is only one build, it is labelled as official.
        For multiple builds without explicit markers, uses ordering
        heuristics to classify them.
        """
        _OFFICIAL = "Official release (astral-sh/uv)"
        _CUSTOM = "Custom build (joelvaneenwyk/uv fork)"
        # A '+' suffix (e.g. "0.7.12+dev") is an explicit custom marker.
        if "+" in ver:
            return _CUSTOM
        # When only one build is present, it is almost certainly official.
        if not has_multiple:
            return _OFFICIAL
        # If another build carries the '+' marker, this clean version
        # is the official release.
        if any_custom_marker:
            return _OFFICIAL
        # Multiple builds, same version string with different hashes --
        # first occurrence is assumed official, others custom.
        if seen_version_strings.get(ver, 1) > 1:
            return _OFFICIAL if occurrence == 1 else _CUSTOM
        # Multiple builds with different version strings and no explicit
        # marker -- first (lowest version) is assumed official, others
        # are custom fork builds.
        return _OFFICIAL if idx == 0 else _CUSTOM

    parts: list[str] = []
    parts.append('<table class="uv-versions-table">')
    parts.append("<thead><tr>")
    parts.append("<th>uv Version</th>")
    parts.append("<th>Source</th>")
    parts.append("<th>Version Hash</th>")
    parts.append("<th>Scenarios</th>")
    parts.append("</tr></thead>")
    parts.append("<tbody>")

    # Track how many times we've seen each version string to label sources
    version_occurrence: dict[str, int] = {}
    has_multiple_builds = len(sorted_versions) > 1

    for idx, (ver, ver_hash) in enumerate(sorted_versions):
        count = version_info[(ver, ver_hash)]
        version_occurrence[ver] = version_occurrence.get(ver, 0) + 1

        source = _infer_source(
            ver, ver_hash, version_occurrence[ver], idx, has_multiple_builds,
        )

        stripped_hash = ver_hash.strip() if ver_hash else ""
        hash_display = _esc(stripped_hash[:12]) if stripped_hash else "N/A"

        parts.append("<tr>")
        parts.append(f"<td><code>{_esc(ver)}</code></td>")
        parts.append(f"<td>{_esc(source)}</td>")
        parts.append(f"<td><code>{hash_display}</code></td>")
        parts.append(f"<td>{count}</td>")
        parts.append("</tr>")

    parts.append("</tbody></table>")
    return "\n".join(parts)


def _render_html_report(
    results: list[ScenarioResult],
    anomaly_map: dict[str, list[Anomaly]],
    ai_summary: str | None,
    ai_provider: str = "",
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

    # Overview / purpose section
    parts.append("<h2>Purpose</h2>")
    parts.append(
        "<p>The primary goal of this report is to <strong>verify that on Windows, "
        "running <code>pythonw.exe</code> or GUI-subsystem scripts does not open "
        "a Console or Terminal window</strong>. This is the fundamental contract "
        "of the GUI subsystem: GUI applications should launch silently without "
        "flashing a console window, even briefly.</p>"
    )
    parts.append(
        "<p><strong>Python Launch Lab</strong> systematically tests every common "
        "way to start a Python process on Windows &mdash; the standard "
        "<code>python.exe</code> / <code>pythonw.exe</code> interpreters, "
        "the <code>uv</code> tool runner (<code>uv run</code>, <code>uvx</code>, "
        "<code>uvw</code>), virtual-environment entry-point wrappers generated by "
        "<code>pip</code> or <code>uv</code>, and the custom <code>pyshim-win</code> "
        "GUI-subsystem shim &mdash; and records whether each launcher creates "
        "a console window, a GUI window, or neither.</p>"
    )
    parts.append(
        "<p>The key questions this report answers:</p>"
    )
    parts.append("<ul>")
    parts.append(
        "<li><strong>Console Window</strong> &mdash; Did Windows allocate a console "
        "host (<code>conhost.exe</code>) for the process? Console (CUI) executables "
        "do this by default; GUI executables <em>should not</em>.</li>"
    )
    parts.append(
        "<li><strong>Application Window</strong> &mdash; Did the application spawn "
        "its own non-console window (e.g. a Tk or Qt window)? Only &ldquo;Yes&rdquo; "
        "when the process itself created a visible application window; "
        "console windows do not count.</li>"
    )
    parts.append(
        "<li><strong>PE Subsystem</strong> &mdash; Is the executable marked as "
        "<code>CUI</code> (console) or <code>GUI</code> (graphical) in its "
        "Portable Executable header? This determines the Windows loader&rsquo;s "
        "default behaviour.</li>"
    )
    parts.append("</ul>")
    parts.append(
        "<p>Rows highlighted in orange indicate <strong>anomalies</strong> &mdash; "
        "cases where observed behaviour differs from what the PE subsystem and "
        "scenario type predict (e.g. a GUI-subsystem launcher unexpectedly "
        "allocating a console window). Expand an anomaly row to see a detailed "
        "explanation of what went wrong and why.</p>"
    )
    parts.append(
        "<p><strong>Related upstream issues &amp; background:</strong></p>"
    )
    parts.append("<ul>")
    parts.append(
        '<li><a href="https://github.com/astral-sh/uv/issues/3957" '
        'target="_blank">astral-sh/uv#3957</a> &mdash; '
        "<code>uv run --script</code> GUI scripts open a console window</li>"
    )
    parts.append(
        '<li><a href="https://github.com/astral-sh/uv/issues/8149" '
        'target="_blank">astral-sh/uv#8149</a> &mdash; '
        "pythonw.exe in uv venvs is a CUI copy instead of GUI subsystem</li>"
    )
    parts.append(
        '<li><a href="https://github.com/astral-sh/uv/issues/4204" '
        'target="_blank">astral-sh/uv#4204</a> &mdash; '
        "GUI entry-point scripts allocated a console on Windows</li>"
    )
    parts.append(
        '<li><a href="https://github.com/pypa/distlib/issues/195" '
        'target="_blank">pypa/distlib#195</a> &mdash; '
        "Windows GUI launchers should use <code>CREATE_NO_WINDOW</code></li>"
    )
    parts.append("</ul>")

    # Issue Diagnosis section
    parts.append("<h2>Issue Diagnosis</h2>")
    parts.append(
        "<p>The custom <code>uv</code> fork builds tested in this report include "
        "targeted fixes for two long-standing Windows GUI launcher issues. "
        "The sections below summarise the root causes and the corresponding "
        "pull-request fixes.</p>"
    )

    parts.append('<div class="issue-diagnosis">')
    parts.append(
        '<h3>\U0001f527 <a href="https://github.com/joelvaneenwyk/uv/pull/2" '
        'target="_blank">PR #2 &mdash; Fix Windows <code>pythonw.exe</code> '
        "venv launcher using console instead of GUI subsystem</a></h3>"
    )
    parts.append(
        "<p><strong>Problem:</strong> When <code>uv</code> created a virtual "
        "environment, the <code>pythonw.exe</code> wrapper inside "
        "<code>.venv/Scripts/</code> was stamped with the <code>CUI</code> "
        "(console) PE subsystem instead of <code>GUI</code>. This caused "
        "Windows to allocate a visible console window every time "
        "<code>pythonw.exe</code> was invoked from the venv &mdash; "
        "defeating the entire purpose of the &ldquo;windowless&rdquo; "
        "interpreter.</p>"
    )
    parts.append(
        "<p><strong>Root cause:</strong> The trampoline executable that "
        "<code>uv</code> embeds as the venv <code>pythonw.exe</code> was "
        "compiled with the default console subsystem. The PE header&rsquo;s "
        "<code>IMAGE_OPTIONAL_HEADER.Subsystem</code> field was set to "
        "<code>IMAGE_SUBSYSTEM_WINDOWS_CUI</code> (3) instead of "
        "<code>IMAGE_SUBSYSTEM_WINDOWS_GUI</code> (2).</p>"
    )
    parts.append(
        "<p><strong>Fix:</strong> The build configuration for the "
        "<code>pythonw.exe</code> trampoline was updated so that its PE "
        "subsystem is <code>GUI</code>. With this change, "
        "<code>.venv/Scripts/pythonw.exe</code> launches without creating "
        "a console window, matching the behaviour of CPython&rsquo;s own "
        "<code>pythonw.exe</code>.</p>"
    )
    parts.append("</div>")

    parts.append('<div class="issue-diagnosis">')
    parts.append(
        '<h3>\U0001f527 <a href="https://github.com/joelvaneenwyk/uv/pull/3" '
        'target="_blank">PR #3 &mdash; Fix GUI script console window: '
        "use <code>CREATE_NO_WINDOW</code> in trampoline for GUI "
        "launchers</a></h3>"
    )
    parts.append(
        "<p><strong>Problem:</strong> Even after ensuring a GUI-subsystem PE "
        "header, entry-point scripts installed via <code>pip install</code> "
        "or <code>uv pip install</code> with <code>gui_scripts</code> still "
        "flashed a console window on startup. The Rust-based trampoline used "
        "by <code>uv</code> to launch these scripts spawned the Python "
        "interpreter as a child process <em>without</em> the "
        "<code>CREATE_NO_WINDOW</code> creation flag.</p>"
    )
    parts.append(
        "<p><strong>Root cause:</strong> The trampoline called "
        "<code>CreateProcessW</code> with <code>dwCreationFlags = 0</code>. "
        "On Windows, when a GUI-subsystem process spawns a CUI child "
        "(such as <code>python.exe</code>), the default behaviour is to "
        "allocate a new console for that child. Without "
        "<code>CREATE_NO_WINDOW</code> (0x08000000), the child inherits a "
        "freshly-created console window, causing the visible flash.</p>"
    )
    parts.append(
        "<p><strong>Fix:</strong> The trampoline&rsquo;s "
        "<code>CreateProcessW</code> call was updated to pass "
        "<code>CREATE_NO_WINDOW</code> in <code>dwCreationFlags</code> when "
        "the launcher is a GUI-subsystem executable. This tells Windows to "
        "run the child process without allocating or displaying a console, "
        "eliminating the flash entirely.</p>"
    )
    parts.append("</div>")

    # uv Versions Tested table
    parts.append("<h2>uv Versions Tested</h2>")
    parts.append(
        "<p>This report includes results from multiple <code>uv</code> builds "
        "run side by side. The table below identifies each version tested "
        "and where it came from. Use the <strong>uv Version</strong> column "
        "filter in the results table to compare behaviour across builds.</p>"
    )
    parts.append(_render_uv_versions_table(results))

    # AI summary (if available)
    if ai_summary:
        if ai_provider == "github-models":
            model_tag = os.environ.get("GITHUB_MODELS_MODEL", "gpt-4o")
            provider_label = "GitHub Models"
        else:
            model_tag = os.environ.get("OLLAMA_MODEL", "llama3.2")
            provider_label = "Ollama"
        parts.append('<div class="ai-summary">')
        parts.append(
            f'<h3>\U0001f916 AI Analysis <span class="model-tag">'
            f'{_esc(provider_label)} / {_esc(model_tag)}</span></h3>'
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

    # Column definitions: (display_name, tooltip)
    columns = [
        ("Scenario", "Unique identifier for the test scenario"),
        ("Status", "Whether the scenario matched expected behaviour or had anomalies"),
        ("Platform", "Operating system platform (e.g. win32, linux)"),
        (
            "uv Version",
            "The uv version string used when this scenario was run. "
            "Multiple rows with the same scenario but different uv version "
            "reflect runs against different uv builds.",
        ),
        (
            "Launcher",
            "The executable used to start the process (python, uv, uvx, venv wrapper, etc.)",
        ),
        ("Command Line", "The full command that was executed for this scenario"),
        ("Exit Code", "Process exit code — 0 means success, non-zero indicates an error"),
        (
            "PE Subsystem",
            "Windows PE subsystem of the resolved executable: CUI (console) or GUI (graphical)",
        ),
        (
            "Console Window",
            "Whether a console window was allocated for the process. "
            "CUI executables get a console by default; GUI executables do not.",
        ),
        (
            "Application Window",
            "Whether the application spawned its own non-console window "
            "(e.g. a Tk or Qt window). Only Yes when the process itself created "
            "a visible application window; console windows do not count.",
        ),
        ("stdout", "Whether the process produced output on its standard output stream"),
        ("stderr", "Whether the process produced output on its standard error stream"),
    ]
    parts.append("<thead>")
    parts.append("<tr>")
    for col_name, col_tip in columns:
        parts.append(
            f'<th title="{_esc(col_tip)}">{_esc(col_name)} '
            f'<span class="sort-arrow">\u21c5</span></th>'
        )
    parts.append("</tr>")

    # Filter row
    parts.append('<tr class="filter-row">')
    parts.append('<th><input type="text" placeholder="Filter\u2026"></th>')
    parts.append(f"<th>{_render_filter_select(unique_vals['status'])}</th>")
    parts.append(f"<th>{_render_filter_select(unique_vals['platform'])}</th>")
    parts.append(f"<th>{_render_filter_select(unique_vals['uv_version'])}</th>")
    parts.append(f"<th>{_render_filter_select(unique_vals['launcher'])}</th>")
    parts.append('<th><input type="text" placeholder="Filter\u2026"></th>')
    parts.append('<th><input type="text" placeholder="Filter\u2026"></th>')
    parts.append(f"<th>{_render_filter_select(unique_vals['subsystem'])}</th>")
    parts.append(f"<th>{_render_filter_select(unique_vals['console'])}</th>")
    parts.append(f"<th>{_render_filter_select(unique_vals['app_window'])}</th>")
    parts.append(f"<th>{_render_filter_select(['Yes', 'No', 'N/A'])}</th>")
    parts.append(f"<th>{_render_filter_select(['Yes', 'No', 'N/A'])}</th>")
    parts.append("</tr>")
    parts.append("</thead>")

    # Data rows
    parts.append("<tbody>")
    for i, r in enumerate(results):
        anomalies = anomaly_map.get(_result_key(r), [])
        row_class = "data-row anomaly-row" if anomalies else "data-row"
        detail_id = f"detail-{i}" if anomalies else ""
        detail_attr = f' data-detail-row="{detail_id}"' if anomalies else ""

        cmd_line = _relative_command_line(r)
        n_columns = len(columns)

        parts.append(f'<tr class="{row_class}"{detail_attr}>')
        parts.append(f"<td>{_esc(r.scenario_id)}</td>")
        parts.append(f"<td>{_status_badge(anomalies)}</td>")
        parts.append(f"<td>{_esc(r.platform)}</td>")
        parts.append(f"<td>{_esc(r.uv_version)}</td>")
        parts.append(f'<td><span class="launcher-tag">{_esc(r.launcher)}</span></td>')
        parts.append(
            f'<td><span class="cmd-line" title="{_esc(cmd_line)}">{_esc(cmd_line)}</span></td>'
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
                f'<td colspan="{n_columns}">'
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
