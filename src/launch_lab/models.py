"""
Result schema for py-launch-lab.

Every scenario produces a ScenarioResult instance that is serialised to JSON
and stored under artifacts/json/.  The schema is kept stable across milestones;
new optional fields may be added but existing ones are never removed.
"""

from __future__ import annotations

from enum import Enum
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field


class Subsystem(str, Enum):
    """Windows PE subsystem classification."""

    GUI = "GUI"
    CUI = "CUI"
    UNKNOWN = "UNKNOWN"
    NOT_PE = "NOT_PE"  # e.g. a script or non-Windows target


class LauncherKind(str, Enum):
    """The top-level launcher used to start the scenario."""

    PYTHON = "python"
    PYTHONW = "pythonw"
    UV = "uv"
    UVW = "uvw"
    UVX = "uvx"
    UV_TOOL_RUN = "uv-tool-run"
    UV_TOOL_INSTALL = "uv-tool-install"
    VENV_DIRECT = "venv-direct"
    SHIM = "pyshim-win"
    UNKNOWN = "unknown"


class ProcessInfo(BaseModel):
    """Snapshot of a single process in the observed process tree."""

    pid: int
    name: str
    exe: Optional[str] = None
    pe_subsystem: Optional[Subsystem] = None
    cmdline: Optional[list[str]] = None


class ScenarioResult(BaseModel):
    """
    Per-scenario result object.

    This is the primary evidence unit emitted by the lab.  Every field that
    cannot be determined on the current platform should be left as None rather
    than guessed.
    """

    # Identity
    scenario_id: str = Field(..., description="Unique identifier for the scenario.")
    platform: str = Field(..., description="sys.platform value (e.g. 'win32', 'linux').")
    python_version: str = Field(..., description="Python version string (e.g. '3.12.3').")
    uv_version: Optional[str] = Field(None, description="uv version string if available.")

    # What was launched
    launcher: LauncherKind = Field(..., description="Top-level launcher kind.")
    mode: str = Field(..., description="Launch mode description (e.g. 'script.py', 'script.pyw').")
    fixture: str = Field(..., description="Fixture name used in the scenario.")

    # Resolution
    resolved_executable: Optional[str] = Field(
        None, description="Absolute path of the executable that was actually invoked."
    )
    resolved_kind: Optional[str] = Field(
        None, description="Human-readable classification of the resolved executable."
    )

    # PE inspection
    pe_subsystem: Optional[Subsystem] = Field(
        None, description="PE subsystem of the resolved executable."
    )

    # Process creation
    creation_flags: Optional[int] = Field(
        None, description="Windows PROCESS_CREATION_FLAGS value used."
    )

    # Observability
    stdout_available: Optional[bool] = Field(
        None, description="Whether the process had a readable stdout stream."
    )
    stderr_available: Optional[bool] = Field(
        None, description="Whether the process had a readable stderr stream."
    )
    visible_window_detected: Optional[bool] = Field(
        None, description="Whether a visible top-level window was detected."
    )
    console_window_detected: Optional[bool] = Field(
        None, description="Whether a console window (conhost/WT) was detected."
    )

    # Process tree
    processes: list[ProcessInfo] = Field(
        default_factory=list,
        description="Snapshot of the observed process tree at time of collection.",
    )

    # Outcome
    exit_code: Optional[int] = Field(None, description="Exit code of the top-level process.")
    stdout_text: Optional[str] = Field(None, description="Captured stdout (truncated if large).")
    stderr_text: Optional[str] = Field(None, description="Captured stderr (truncated if large).")
    notes: Optional[str] = Field(None, description="Free-text notes about the scenario run.")

    model_config = ConfigDict(use_enum_values=True)
