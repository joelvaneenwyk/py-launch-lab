"""
Expected behaviour definitions for py-launch-lab scenarios.

Each scenario has an expected set of observable properties.  The HTML report
compares actual results against these expectations and highlights anomalies.
"""

from __future__ import annotations

from dataclasses import dataclass

from launch_lab.models import ScenarioResult, Subsystem


@dataclass(frozen=True)
class ExpectedBehaviour:
    """What we expect a scenario to produce on a correctly-behaving system."""

    pe_subsystem: Subsystem | None = None
    console_window: bool | None = None
    visible_window: bool | None = None
    stdout_available: bool | None = None
    exit_code: int = 0
    explanation: str = ""
    doc_url: str = ""


# ---------------------------------------------------------------------------
# Per-scenario expectations
# ---------------------------------------------------------------------------
# Key: scenario_id → ExpectedBehaviour
#
# These encode the *correct* Windows launch semantics.  When a result deviates
# from its expectation the report highlights the row and shows an explanation
# bubble.

EXPECTATIONS: dict[str, ExpectedBehaviour] = {
    # --- Direct python / pythonw ---
    "python-script-py": ExpectedBehaviour(
        pe_subsystem=Subsystem.CUI,
        console_window=True,
        stdout_available=True,
        exit_code=0,
        explanation=(
            "python.exe is a CUI (console) binary.  When launched, Windows should "
            "allocate a console window and stdout should be available."
        ),
        doc_url="https://docs.python.org/3/using/windows.html",
    ),
    "python-script-pyw": ExpectedBehaviour(
        pe_subsystem=Subsystem.CUI,
        console_window=True,
        stdout_available=False,
        exit_code=0,
        explanation=(
            "python.exe running a .pyw file still runs under the CUI subsystem. "
            "stdout is typically not produced because .pyw scripts suppress output, "
            "but a console window should still be allocated by the OS."
        ),
        doc_url="https://docs.python.org/3/using/windows.html",
    ),
    "pythonw-script-py": ExpectedBehaviour(
        pe_subsystem=Subsystem.GUI,
        console_window=False,
        stdout_available=True,
        exit_code=0,
        explanation=(
            "pythonw.exe is a GUI-subsystem binary.  It should NOT create a console "
            "window.  stdout is still captured via pipes in our test harness, but "
            "in a normal double-click launch there would be no visible console."
        ),
        doc_url="https://docs.python.org/3/using/windows.html",
    ),
    "pythonw-script-pyw": ExpectedBehaviour(
        pe_subsystem=Subsystem.GUI,
        console_window=False,
        stdout_available=False,
        exit_code=0,
        explanation=(
            "pythonw.exe running a .pyw script: GUI subsystem, no console, no stdout.  "
            "This is the canonical silent-launch mode on Windows."
        ),
        doc_url="https://docs.python.org/3/using/windows.html",
    ),
    # --- uv run ---
    "uv-run-script-py": ExpectedBehaviour(
        pe_subsystem=Subsystem.CUI,
        console_window=True,
        stdout_available=True,
        exit_code=0,
        explanation=(
            "uv.exe is a CUI binary.  'uv run hello.py' should behave like "
            "'python hello.py' — console window present, stdout captured."
        ),
        doc_url="https://docs.astral.sh/uv/reference/cli/#uv-run",
    ),
    "uv-run-script-pyw": ExpectedBehaviour(
        pe_subsystem=Subsystem.CUI,
        console_window=True,
        stdout_available=False,
        exit_code=0,
        explanation=(
            "uv.exe running a .pyw file: uv itself is CUI so a console is allocated, "
            "but the .pyw script does not write to stdout."
        ),
        doc_url="https://docs.astral.sh/uv/reference/cli/#uv-run",
    ),
    "uv-run-gui-script": ExpectedBehaviour(
        pe_subsystem=Subsystem.CUI,
        console_window=True,
        stdout_available=True,
        exit_code=0,
        explanation=(
            "'uv run --gui-script hello.py' is intended to launch via pythonw, but "
            "because uv.exe itself is CUI, a console window is still created by the "
            "OS.  This is a known uv limitation — ideally no console should appear."
        ),
        doc_url="https://docs.astral.sh/uv/reference/cli/#uv-run",
    ),
    # --- uv tool ---
    "uv-tool-install-console": ExpectedBehaviour(
        pe_subsystem=Subsystem.CUI,
        console_window=True,
        stdout_available=False,
        exit_code=0,
        explanation=(
            "'uv tool install' for a console package.  uv writes progress to stderr; "
            "no stdout expected from the install command itself."
        ),
        doc_url="https://docs.astral.sh/uv/reference/cli/#uv-tool-install",
    ),
    "uv-tool-install-gui": ExpectedBehaviour(
        pe_subsystem=Subsystem.CUI,
        console_window=True,
        stdout_available=False,
        exit_code=0,
        explanation=(
            "'uv tool install' for a GUI package.  Even for GUI packages, "
            "uv.exe is CUI so a console window appears.  The installed GUI "
            "entry-point should itself be GUI-subsystem, but the *install* "
            "command always runs under uv.exe (CUI)."
        ),
        doc_url="https://docs.astral.sh/uv/reference/cli/#uv-tool-install",
    ),
    "uv-tool-run-pkg-console": ExpectedBehaviour(
        pe_subsystem=Subsystem.CUI,
        console_window=True,
        stdout_available=True,
        exit_code=0,
        explanation=(
            "'uv tool run --from pkg_console lab-console': uv runs the console "
            "entrypoint in an ephemeral venv.  CUI subsystem, console visible."
        ),
        doc_url="https://docs.astral.sh/uv/reference/cli/#uv-tool-run",
    ),
    # --- uvw ---
    "uvw-run-script-py": ExpectedBehaviour(
        pe_subsystem=Subsystem.GUI,
        console_window=False,
        stdout_available=True,
        exit_code=0,
        explanation=(
            "uvw.exe is the GUI-subsystem counterpart to uv.exe.  It should NOT "
            "allocate a console window.  This mirrors the python/pythonw split."
        ),
        doc_url="https://docs.astral.sh/uv/reference/cli/#uv-run",
    ),
    # --- uvx ---
    "uvx-pkg-console": ExpectedBehaviour(
        pe_subsystem=Subsystem.CUI,
        console_window=True,
        stdout_available=True,
        exit_code=0,
        explanation=(
            "'uvx --from pkg_console lab-console': shorthand for 'uv tool run'.  "
            "CUI subsystem, console visible, stdout captured."
        ),
        doc_url="https://docs.astral.sh/uv/reference/cli/#uvx",
    ),
    # --- venv-direct ---
    "venv-console-entrypoint": ExpectedBehaviour(
        pe_subsystem=Subsystem.CUI,
        console_window=True,
        stdout_available=True,
        exit_code=0,
        explanation=(
            "Console entry-point wrapper in a venv (pip-generated .exe).  "
            "The wrapper is CUI so Windows allocates a console."
        ),
    ),
    "venv-gui-entrypoint": ExpectedBehaviour(
        pe_subsystem=Subsystem.GUI,
        console_window=False,
        visible_window=True,
        stdout_available=False,
        exit_code=0,
        explanation=(
            "GUI entry-point wrapper in a venv (pip/uv-generated .exe with GUI "
            "subsystem).  The wrapper itself is GUI, so Windows does not auto-allocate "
            "a console for it.  However, the wrapper internally launches the venv's "
            "pythonw.exe — if that binary is a CUI copy (as in uv venvs), a console "
            "window WILL flash because the child process triggers console allocation.  "
            "This is a known uv bug where the venv pythonw.exe is not actually "
            "GUI-subsystem.  Investigation: https://github.com/joelvaneenwyk/uv/issues/1  "
            "Fix in progress: https://github.com/joelvaneenwyk/uv/pull/2"
        ),
        doc_url="https://github.com/astral-sh/uv/issues/9781",
    ),
    "venv-dual-console-entrypoint": ExpectedBehaviour(
        pe_subsystem=Subsystem.CUI,
        console_window=True,
        stdout_available=True,
        exit_code=0,
        explanation=("Dual-mode package console entry-point.  The console wrapper is CUI."),
    ),
    "venv-dual-gui-entrypoint": ExpectedBehaviour(
        pe_subsystem=Subsystem.GUI,
        console_window=False,
        visible_window=False,
        stdout_available=False,
        exit_code=0,
        explanation=(
            "Dual-mode package GUI entry-point.  The GUI wrapper should not "
            "create a console.  However, if the venv's pythonw.exe is actually "
            "a CUI binary (uv venv bug), the child process WILL allocate a "
            "console window — appearing as an unwanted terminal flash.  "
            "Investigation: https://github.com/joelvaneenwyk/uv/issues/1  "
            "Fix in progress: https://github.com/joelvaneenwyk/uv/pull/2"
        ),
        doc_url="https://github.com/astral-sh/uv/issues/9781",
    ),
    "venv-python-script-py": ExpectedBehaviour(
        pe_subsystem=Subsystem.CUI,
        console_window=True,
        stdout_available=True,
        exit_code=0,
        explanation=(
            "Running hello.py via the venv python.exe.  The venv python.exe is a "
            "CUI binary (copy or symlink of the system python.exe)."
        ),
    ),
    "venv-pythonw-script-py": ExpectedBehaviour(
        pe_subsystem=Subsystem.CUI,
        console_window=False,
        stdout_available=True,
        exit_code=0,
        explanation=(
            "Running hello.py via the venv pythonw.exe.  On Windows the venv "
            "pythonw.exe SHOULD be a GUI-subsystem binary (no console window).  "
            "However, some venv implementations (including uv) create a CUI shim "
            "instead, which means a console window flashes — this is a known bug.  "
            "If the PE subsystem shows CUI instead of GUI, that's the issue.  "
            "Investigation: https://github.com/joelvaneenwyk/uv/issues/1  "
            "Fix in progress: https://github.com/joelvaneenwyk/uv/pull/2"
        ),
        doc_url="https://github.com/astral-sh/uv/issues/9781",
    ),
    # --- shim ---
    "shim-python-script-py": ExpectedBehaviour(
        pe_subsystem=Subsystem.GUI,
        console_window=False,
        stdout_available=True,
        exit_code=0,
        explanation=(
            "pyshim-win wraps python.exe with --hide-console.  The shim itself is "
            "a GUI-subsystem binary that suppresses the console window."
        ),
    ),
    "shim-uv-run-script-py": ExpectedBehaviour(
        pe_subsystem=Subsystem.GUI,
        console_window=False,
        stdout_available=True,
        exit_code=0,
        explanation=(
            "pyshim-win wraps 'uv run' with --hide-console.  Despite uv.exe being "
            "CUI, the shim suppresses the console allocation."
        ),
    ),
}


@dataclass
class Anomaly:
    """A single deviation from expected behaviour."""

    field: str
    expected: str
    actual: str
    explanation: str
    doc_url: str = ""


def check_expectations(result: ScenarioResult) -> list[Anomaly]:
    """Compare a result against its expected behaviour.

    Returns a list of anomalies (empty if everything matches).
    """
    expected = EXPECTATIONS.get(result.scenario_id)
    if expected is None:
        return []

    anomalies: list[Anomaly] = []

    if expected.exit_code is not None and result.exit_code != expected.exit_code:
        anomalies.append(
            Anomaly(
                field="Exit Code",
                expected=str(expected.exit_code),
                actual=str(result.exit_code),
                explanation=expected.explanation,
                doc_url=expected.doc_url,
            )
        )

    if expected.pe_subsystem is not None and result.pe_subsystem != expected.pe_subsystem:
        anomalies.append(
            Anomaly(
                field="PE Subsystem",
                expected=expected.pe_subsystem.value,
                actual=str(result.pe_subsystem) if result.pe_subsystem else "N/A",
                explanation=expected.explanation,
                doc_url=expected.doc_url,
            )
        )

    if (
        expected.console_window is not None
        and result.console_window_detected is not None
        and result.console_window_detected != expected.console_window
    ):
        anomalies.append(
            Anomaly(
                field="Console Window",
                expected="Yes" if expected.console_window else "No",
                actual="Yes" if result.console_window_detected else "No",
                explanation=expected.explanation,
                doc_url=expected.doc_url,
            )
        )

    if (
        expected.visible_window is not None
        and result.visible_window_detected is not None
        and result.visible_window_detected != expected.visible_window
    ):
        anomalies.append(
            Anomaly(
                field="Visible Window",
                expected="Yes" if expected.visible_window else "No",
                actual="Yes" if result.visible_window_detected else "No",
                explanation=expected.explanation,
                doc_url=expected.doc_url,
            )
        )

    if (
        expected.stdout_available is not None
        and result.stdout_available is not None
        and result.stdout_available != expected.stdout_available
    ):
        anomalies.append(
            Anomaly(
                field="stdout",
                expected="Yes" if expected.stdout_available else "No",
                actual="Yes" if result.stdout_available else "No",
                explanation=expected.explanation,
                doc_url=expected.doc_url,
            )
        )

    return anomalies
