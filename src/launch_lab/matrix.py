"""
Scenario matrix for py-launch-lab.

Scenarios are plain data objects.  New scenarios are added here; runner.py
and collect.py do not need to change.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class Scenario:
    """
    Definition of a single runnable scenario.

    A scenario combines a launcher, a mode, and a fixture into a unique,
    stable scenario_id that is used as the primary key in result artifacts.
    """

    scenario_id: str
    launcher: str
    mode: str
    fixture: str
    args: list[str] = field(default_factory=list)
    description: str = ""
    windows_only: bool = False
    requires_uv: bool = False
    skip_reason: str | None = None


# ---------------------------------------------------------------------------
# Scenario definitions
# ---------------------------------------------------------------------------

_SCENARIOS: list[Scenario] = [
    # --- Direct python / pythonw ---
    Scenario(
        scenario_id="python-script-py",
        launcher="python",
        mode="script.py",
        fixture="raw_py",
        args=["fixtures/raw_py/hello.py"],
        description="python hello.py — expect console window, stdout available",
    ),
    Scenario(
        scenario_id="python-script-pyw",
        launcher="python",
        mode="script.pyw",
        fixture="raw_pyw",
        args=["fixtures/raw_pyw/hello.pyw"],
        description="python hello.pyw — py launcher may invoke pythonw",
        windows_only=True,
    ),
    Scenario(
        scenario_id="pythonw-script-py",
        launcher="pythonw",
        mode="script.py",
        fixture="raw_py",
        args=["fixtures/raw_py/hello.py"],
        description="pythonw hello.py — GUI subsystem, no console window",
        windows_only=True,
    ),
    Scenario(
        scenario_id="pythonw-script-pyw",
        launcher="pythonw",
        mode="script.pyw",
        fixture="raw_pyw",
        args=["fixtures/raw_pyw/hello.pyw"],
        description="pythonw hello.pyw — GUI subsystem, no console window",
        windows_only=True,
    ),
    # --- uv run ---
    Scenario(
        scenario_id="uv-run-script-py",
        launcher="uv",
        mode="run script.py",
        fixture="raw_py",
        args=["run", "fixtures/raw_py/hello.py"],
        description="uv run hello.py",
        requires_uv=True,
    ),
    Scenario(
        scenario_id="uv-run-script-pyw",
        launcher="uv",
        mode="run script.pyw",
        fixture="raw_pyw",
        args=["run", "fixtures/raw_pyw/hello.pyw"],
        description="uv run hello.pyw",
        requires_uv=True,
    ),
    Scenario(
        scenario_id="uv-run-gui-script",
        launcher="uv",
        mode="run --gui-script script.py",
        fixture="raw_py",
        args=["run", "--gui-script", "fixtures/raw_py/hello.py"],
        description="uv run --gui-script hello.py",
        requires_uv=True,
        windows_only=True,
    ),
    # --- uvw run ---
    Scenario(
        scenario_id="uvw-run-script-py",
        launcher="uvw",
        mode="run script.py",
        fixture="raw_py",
        args=["run", "fixtures/raw_py/hello.py"],
        description="uvw run hello.py",
        requires_uv=True,
        windows_only=True,
    ),
    # --- uvx / uv tool run ---
    Scenario(
        scenario_id="uvx-pkg-console",
        launcher="uvx",
        mode="tool run console fixture",
        fixture="pkg_console",
        args=["--from", "fixtures/pkg_console", "lab-console"],
        description="uvx --from pkg_console lab-console",
        requires_uv=True,
    ),
    Scenario(
        scenario_id="uv-tool-run-pkg-console",
        launcher="uv",
        mode="tool run console fixture",
        fixture="pkg_console",
        args=["tool", "run", "--from", "fixtures/pkg_console", "lab-console"],
        description="uv tool run --from pkg_console lab-console",
        requires_uv=True,
    ),
    # --- uv tool install ---
    Scenario(
        scenario_id="uv-tool-install-console",
        launcher="uv",
        mode="tool install console fixture",
        fixture="pkg_console",
        args=["tool", "install", "--editable", "fixtures/pkg_console"],
        description="uv tool install pkg_console (console entrypoint)",
        requires_uv=True,
    ),
    Scenario(
        scenario_id="uv-tool-install-gui",
        launcher="uv",
        mode="tool install gui fixture",
        fixture="pkg_gui",
        args=["tool", "install", "--editable", "fixtures/pkg_gui"],
        description="uv tool install pkg_gui (GUI entrypoint)",
        requires_uv=True,
        windows_only=True,
    ),
    # --- venv-direct scenarios ---
    # These scenarios require a dynamically-created virtual environment and are
    # therefore skipped by the matrix runner.  The corresponding integration
    # tests (tests/integration/test_venv.py) create a temporary venv, install
    # fixture packages, and exercise the generated executables directly.
    Scenario(
        scenario_id="venv-python-script-py",
        launcher="venv-direct",
        mode="venv python script.py",
        fixture="raw_py",
        args=[],  # populated dynamically by test
        description=(
            "Run hello.py via the venv's python executable. "
            "On Windows the venv python.exe is a CUI copy/symlink; "
            "it should produce a console window and stdout."
        ),
        skip_reason="Requires dynamic venv setup (see tests/integration/test_venv.py)",
    ),
    Scenario(
        scenario_id="venv-pythonw-script-py",
        launcher="venv-direct",
        mode="venv pythonw script.py",
        fixture="raw_py",
        args=[],
        description=(
            "Run hello.py via the venv's pythonw executable. "
            "On Windows the venv pythonw.exe is a GUI-subsystem copy/symlink; "
            "it should NOT produce a console window."
        ),
        windows_only=True,
        skip_reason="Requires dynamic venv setup (see tests/integration/test_venv.py)",
    ),
    Scenario(
        scenario_id="venv-console-entrypoint",
        launcher="venv-direct",
        mode="venv project.scripts entrypoint",
        fixture="pkg_console",
        args=[],
        description=(
            "Install pkg_console (project.scripts) into a venv and run the "
            "generated console-script wrapper. On Windows the wrapper is a "
            "CUI .exe that should create a console window."
        ),
        skip_reason="Requires dynamic venv setup (see tests/integration/test_venv.py)",
    ),
    Scenario(
        scenario_id="venv-gui-entrypoint",
        launcher="venv-direct",
        mode="venv project.gui-scripts entrypoint",
        fixture="pkg_gui",
        args=[],
        description=(
            "Install pkg_gui (project.gui-scripts) into a venv and run the "
            "generated GUI-script wrapper. On Windows the wrapper is a "
            "GUI .exe (no console window)."
        ),
        windows_only=True,
        skip_reason="Requires dynamic venv setup (see tests/integration/test_venv.py)",
    ),
    Scenario(
        scenario_id="venv-dual-console-entrypoint",
        launcher="venv-direct",
        mode="venv dual project.scripts entrypoint",
        fixture="pkg_dual",
        args=[],
        description=(
            "Install pkg_dual (project.scripts + project.gui-scripts) into a "
            "venv and run the console entrypoint. On Windows the wrapper is a "
            "CUI .exe."
        ),
        skip_reason="Requires dynamic venv setup (see tests/integration/test_venv.py)",
    ),
    Scenario(
        scenario_id="venv-dual-gui-entrypoint",
        launcher="venv-direct",
        mode="venv dual project.gui-scripts entrypoint",
        fixture="pkg_dual",
        args=[],
        description=(
            "Install pkg_dual (project.scripts + project.gui-scripts) into a "
            "venv and run the GUI entrypoint. On Windows the wrapper is a "
            "GUI .exe (no console window)."
        ),
        windows_only=True,
        skip_reason="Requires dynamic venv setup (see tests/integration/test_venv.py)",
    ),
    # --- Shim-wrapped variants ---
    Scenario(
        scenario_id="shim-python-script-py",
        launcher="pyshim-win",
        mode="--hide-console python script.py",
        fixture="raw_py",
        args=["--hide-console", "--", "python", "fixtures/raw_py/hello.py"],
        description="pyshim-win --hide-console -- python hello.py",
        windows_only=True,
    ),
    Scenario(
        scenario_id="shim-uv-run-script-py",
        launcher="pyshim-win",
        mode="--hide-console uv run script.py",
        fixture="raw_py",
        args=["--hide-console", "--", "uv", "run", "fixtures/raw_py/hello.py"],
        description="pyshim-win --hide-console -- uv run hello.py",
        windows_only=True,
        requires_uv=True,
    ),
]


def get_matrix() -> list[Scenario]:
    """Return the full scenario list."""
    return list(_SCENARIOS)


def get_scenario(scenario_id: str) -> Scenario | None:
    """Look up a scenario by its ID.  Returns None if not found."""
    for s in _SCENARIOS:
        if s.scenario_id == scenario_id:
            return s
    return None
