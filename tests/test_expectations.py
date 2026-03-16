"""
Tests for the expectations module — single source of truth validation.

These tests verify that:
  1. Every scenario in the matrix has a matching expectation.
  2. The ``check_expectations`` function correctly detects anomalies.
  3. Known deviations are properly documented.
  4. The helper functions (``is_known_deviation``, ``get_known_deviations``)
     work as expected.

For *integration* tests that run real scenarios and compare results against
expectations, see ``tests/integration/``.
"""

from __future__ import annotations

import pytest

from launch_lab.expectations import (
    EXPECTATIONS,
    KNOWN_DEVIATIONS,
    Anomaly,
    ExpectedBehaviour,
    KnownDeviation,
    check_expectations,
    get_known_deviations,
    is_known_deviation,
)
from launch_lab.matrix import get_matrix, get_scenario
from launch_lab.models import LauncherKind, ScenarioResult, Subsystem


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_result(**kwargs) -> ScenarioResult:
    defaults = dict(
        scenario_id="test-scenario",
        platform="win32",
        python_version="3.12.0",
        launcher=LauncherKind.PYTHON,
        mode="script.py",
        fixture="raw_py",
    )
    defaults.update(kwargs)
    return ScenarioResult(**defaults)


# ---------------------------------------------------------------------------
# 1. Coverage: every matrix scenario has an expectation
# ---------------------------------------------------------------------------


def test_all_matrix_scenarios_have_expectations():
    """Every scenario defined in matrix.py should have a matching entry in EXPECTATIONS."""
    scenario_ids = {s.scenario_id for s in get_matrix()}
    expectation_ids = set(EXPECTATIONS.keys())
    missing = scenario_ids - expectation_ids
    assert not missing, (
        f"Scenarios missing expectations: {sorted(missing)}.  "
        f"Add entries to EXPECTATIONS in expectations.py."
    )


def test_no_orphan_expectations():
    """Every expectation key should correspond to a scenario in the matrix."""
    scenario_ids = {s.scenario_id for s in get_matrix()}
    expectation_ids = set(EXPECTATIONS.keys())
    orphans = expectation_ids - scenario_ids
    assert not orphans, (
        f"Orphan expectations (no matching scenario): {sorted(orphans)}.  "
        f"Remove stale entries from EXPECTATIONS."
    )


# ---------------------------------------------------------------------------
# 2. check_expectations detects anomalies
# ---------------------------------------------------------------------------


class TestCheckExpectations:
    """Verify the anomaly detection engine."""

    def test_no_anomaly_when_result_matches(self):
        """A result that matches expectations should produce zero anomalies."""
        result = _make_result(
            scenario_id="python-script-py",
            exit_code=0,
            pe_subsystem=Subsystem.CUI,
            console_window_detected=True,
            stdout_available=True,
        )
        anomalies = check_expectations(result)
        assert anomalies == []

    def test_anomaly_on_wrong_exit_code(self):
        result = _make_result(
            scenario_id="python-script-py",
            exit_code=1,
            pe_subsystem=Subsystem.CUI,
        )
        anomalies = check_expectations(result)
        fields = [a.field for a in anomalies]
        assert "Exit Code" in fields

    def test_anomaly_on_wrong_pe_subsystem(self):
        result = _make_result(
            scenario_id="python-script-py",
            exit_code=0,
            pe_subsystem=Subsystem.GUI,  # should be CUI
        )
        anomalies = check_expectations(result)
        fields = [a.field for a in anomalies]
        assert "PE Subsystem" in fields

    def test_anomaly_on_wrong_console_window(self):
        result = _make_result(
            scenario_id="python-script-py",
            exit_code=0,
            pe_subsystem=Subsystem.CUI,
            console_window_detected=False,  # should be True
        )
        anomalies = check_expectations(result)
        fields = [a.field for a in anomalies]
        assert "Console Window" in fields

    def test_anomaly_on_wrong_stdout(self):
        result = _make_result(
            scenario_id="python-script-py",
            exit_code=0,
            pe_subsystem=Subsystem.CUI,
            stdout_available=False,  # should be True
        )
        anomalies = check_expectations(result)
        fields = [a.field for a in anomalies]
        assert "stdout" in fields

    def test_no_anomaly_for_unknown_scenario(self):
        """Unknown scenario_ids should produce zero anomalies (no expectation)."""
        result = _make_result(scenario_id="nonexistent-scenario", exit_code=99)
        assert check_expectations(result) == []

    def test_none_fields_not_flagged(self):
        """When observed fields are None (not detected), no anomaly is raised."""
        result = _make_result(
            scenario_id="python-script-py",
            exit_code=0,
            pe_subsystem=Subsystem.CUI,
            console_window_detected=None,
            visible_window_detected=None,
            stdout_available=None,
        )
        anomalies = check_expectations(result)
        assert anomalies == []

    def test_venv_pythonw_ideal_is_gui(self):
        """The expectation for venv-pythonw-script-py should require GUI subsystem.

        This validates that we encode *ideal* behaviour: pythonw.exe in a
        venv should be a GUI-subsystem binary, not a CUI trampoline.
        """
        expected = EXPECTATIONS["venv-pythonw-script-py"]
        assert expected.pe_subsystem == Subsystem.GUI
        assert expected.console_window is False

    def test_venv_gui_entrypoint_ideal_no_console(self):
        """GUI entry-points should ideally NOT open a console window."""
        expected = EXPECTATIONS["venv-gui-entrypoint"]
        assert expected.pe_subsystem == Subsystem.GUI
        assert expected.console_window is False

    def test_venv_dual_gui_ideal_no_console(self):
        """Dual-mode GUI entry-points should ideally NOT open a console window."""
        expected = EXPECTATIONS["venv-dual-gui-entrypoint"]
        assert expected.pe_subsystem == Subsystem.GUI
        assert expected.console_window is False


# ---------------------------------------------------------------------------
# 3. Known deviations are documented
# ---------------------------------------------------------------------------


class TestKnownDeviations:
    """Verify the known-deviations registry."""

    def test_all_deviation_scenarios_exist_in_expectations(self):
        """Every scenario in KNOWN_DEVIATIONS must have a matching expectation."""
        for scenario_id in KNOWN_DEVIATIONS:
            assert scenario_id in EXPECTATIONS, (
                f"KNOWN_DEVIATIONS references '{scenario_id}' which has no expectation."
            )

    def test_deviation_fields_match_expectation_fields(self):
        """Each deviation's ``field`` should correspond to an ExpectedBehaviour attribute."""
        valid_fields = {
            "pe_subsystem",
            "console_window",
            "application_window",
            "stdout_available",
            "exit_code",
        }
        # The field names in Anomaly use display names; map them
        display_to_attr = {
            "pe_subsystem": "pe_subsystem",
            "console_window": "console_window",
            "application_window": "application_window",
            "stdout_available": "stdout_available",
            "exit_code": "exit_code",
        }
        for scenario_id, devs in KNOWN_DEVIATIONS.items():
            for dev in devs:
                assert dev.field in valid_fields, (
                    f"KNOWN_DEVIATIONS['{scenario_id}'] has invalid field '{dev.field}'.  "
                    f"Valid: {valid_fields}"
                )

    def test_every_deviation_has_issue_url(self):
        """Every known deviation should reference an upstream issue."""
        for scenario_id, devs in KNOWN_DEVIATIONS.items():
            for dev in devs:
                assert dev.issue_url, (
                    f"KNOWN_DEVIATIONS['{scenario_id}'].{dev.field} missing issue_url"
                )

    def test_venv_pythonw_has_pe_subsystem_deviation(self):
        """Stock uv creates pythonw.exe as CUI — this should be a known deviation."""
        dev = is_known_deviation("venv-pythonw-script-py", "pe_subsystem")
        assert dev is not None
        assert dev.ideal_value == "GUI"
        assert dev.actual_value == "CUI"

    def test_venv_gui_has_console_window_deviation(self):
        """Stock uv's CUI pythonw causes GUI wrappers to flash a console."""
        dev = is_known_deviation("venv-gui-entrypoint", "console_window")
        assert dev is not None
        assert dev.ideal_value == "No"
        assert dev.actual_value == "Yes"


# ---------------------------------------------------------------------------
# 4. Helper functions
# ---------------------------------------------------------------------------


class TestHelperFunctions:
    """Verify the helper functions."""

    def test_is_known_deviation_returns_none_for_clean_scenario(self):
        assert is_known_deviation("python-script-py", "pe_subsystem") is None

    def test_is_known_deviation_returns_none_for_wrong_field(self):
        assert is_known_deviation("venv-pythonw-script-py", "exit_code") is None

    def test_is_known_deviation_returns_deviation(self):
        dev = is_known_deviation("venv-pythonw-script-py", "pe_subsystem")
        assert isinstance(dev, KnownDeviation)

    def test_get_known_deviations_empty_for_clean(self):
        assert get_known_deviations("python-script-py") == []

    def test_get_known_deviations_returns_list(self):
        devs = get_known_deviations("venv-pythonw-script-py")
        assert len(devs) >= 1
        assert all(isinstance(d, KnownDeviation) for d in devs)

    def test_get_known_deviations_unknown_scenario(self):
        assert get_known_deviations("nonexistent") == []


# ---------------------------------------------------------------------------
# 5. Ideal-behaviour parametrised validation
# ---------------------------------------------------------------------------
# These tests document what *should* be true.  They are parametrised over
# all expectations so that every scenario's ideal is explicitly asserted.


_GUI_SCENARIOS = [sid for sid, exp in EXPECTATIONS.items() if exp.pe_subsystem == Subsystem.GUI]

_NO_CONSOLE_SCENARIOS = [sid for sid, exp in EXPECTATIONS.items() if exp.console_window is False]


@pytest.mark.parametrize("scenario_id", _GUI_SCENARIOS)
def test_gui_scenarios_expect_no_console(scenario_id: str):
    """Every scenario with a GUI PE subsystem should expect no console window.

    This is a cross-check: if a scenario's launcher is GUI-subsystem, then
    Windows should not allocate a console window for it.
    """
    exp = EXPECTATIONS[scenario_id]
    assert exp.console_window is False, (
        f"Scenario '{scenario_id}' has pe_subsystem=GUI but console_window={exp.console_window}.  "
        f"GUI executables should not allocate a console window."
    )


@pytest.mark.parametrize("scenario_id", _NO_CONSOLE_SCENARIOS)
def test_no_console_scenarios_are_gui(scenario_id: str):
    """Every scenario that expects no console window should have a GUI PE subsystem.

    CUI executables always get a console from Windows; only GUI executables
    can run without one.
    """
    exp = EXPECTATIONS[scenario_id]
    assert exp.pe_subsystem == Subsystem.GUI, (
        f"Scenario '{scenario_id}' expects console_window=False but "
        f"pe_subsystem={exp.pe_subsystem}.  Only GUI executables run without a console."
    )
