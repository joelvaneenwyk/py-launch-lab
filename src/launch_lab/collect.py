"""
Artifact collector for py-launch-lab.

Serialises a ScenarioResult to JSON and writes it to the artifacts directory.

When the result contains a ``uv_version_hash``, the file is written as
``<scenario-id>__<hash>.json`` so that results from different uv builds
(including custom branches or repos) coexist in the same directory without
overwriting each other.  This makes artifacts durable across multiple runs
with different uv versions.
"""

from __future__ import annotations

import json
from pathlib import Path

from launch_lab.models import ScenarioResult

_DEFAULT_JSON_DIR = Path("artifacts/json")


def artifact_filename(result: ScenarioResult) -> str:
    """Return the filename for a ScenarioResult artifact.

    When ``uv_version_hash`` is set the filename is
    ``<scenario-id>__<hash>.json`` so that results from different uv
    builds coexist in the same directory.  Otherwise the legacy
    ``<scenario-id>.json`` form is used for backward compatibility.
    """
    if result.uv_version_hash:
        return f"{result.scenario_id}__{result.uv_version_hash}.json"
    return f"{result.scenario_id}.json"


def save_result(result: ScenarioResult, output_dir: Path = _DEFAULT_JSON_DIR) -> Path:
    """
    Serialise a ScenarioResult to JSON and write it to output_dir.

    The filename is determined by :func:`artifact_filename`.

    Returns the path of the written file.
    """
    output_dir.mkdir(parents=True, exist_ok=True)
    dest = output_dir / artifact_filename(result)
    dest.write_text(result.model_dump_json(indent=2), encoding="utf-8")
    return dest


def load_result(path: Path) -> ScenarioResult:
    """Load a ScenarioResult from a JSON file."""
    data = json.loads(path.read_text(encoding="utf-8"))
    return ScenarioResult.model_validate(data)


def load_all_results(json_dir: Path = _DEFAULT_JSON_DIR) -> list[ScenarioResult]:
    """Load all results from a directory of JSON files."""
    results = []
    for p in sorted(json_dir.glob("*.json")):
        try:
            results.append(load_result(p))
        except (OSError, ValueError, KeyError) as exc:
            # Skip malformed or unreadable files; caller can inspect the directory
            # directly if detailed diagnostics are needed.
            _ = exc
    return results
