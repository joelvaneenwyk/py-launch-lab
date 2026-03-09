"""
Shared utilities for py-launch-lab.
"""

from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path
from typing import Optional


def find_executable(name: str) -> Optional[Path]:
    """Return the absolute path of `name` on PATH, or None."""
    found = shutil.which(name)
    return Path(found) if found else None


def run_quiet(
    cmd: list[str],
    timeout: float = 10.0,
) -> tuple[int, str, str]:
    """
    Run a command, capturing stdout and stderr.

    Returns (returncode, stdout, stderr).
    """
    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
        return result.returncode, result.stdout, result.stderr
    except FileNotFoundError:
        return -1, "", f"Executable not found: {cmd[0]}"
    except subprocess.TimeoutExpired:
        return -1, "", f"Timed out after {timeout}s"


def platform_note() -> str:
    """Return a human-readable platform string."""
    return f"{sys.platform} / Python {sys.version_info.major}.{sys.version_info.minor}"
