"""
Tests for the scenario matrix (matrix.py).

These tests check that scenario definitions are well-formed, unique, and
consistent.  They do not run any processes.
"""

import pytest

from launch_lab.matrix import Scenario, get_matrix, get_scenario


def test_matrix_is_non_empty():
    matrix = get_matrix()
    assert len(matrix) > 0


def test_scenario_ids_are_unique():
    ids = [s.scenario_id for s in get_matrix()]
    assert len(ids) == len(set(ids)), "Duplicate scenario_id found"


def test_all_scenarios_have_required_fields():
    for s in get_matrix():
        assert s.scenario_id, f"Empty scenario_id: {s}"
        assert s.launcher, f"Empty launcher in {s.scenario_id}"
        assert s.mode, f"Empty mode in {s.scenario_id}"
        assert s.fixture, f"Empty fixture in {s.scenario_id}"


def test_get_scenario_by_id():
    matrix = get_matrix()
    first = matrix[0]
    found = get_scenario(first.scenario_id)
    assert found is not None
    assert found.scenario_id == first.scenario_id


def test_get_scenario_missing_returns_none():
    assert get_scenario("no-such-scenario-xyz") is None


def test_known_scenario_python_script_py():
    s = get_scenario("python-script-py")
    assert s is not None
    assert s.launcher == "python"
    assert s.fixture == "raw_py"


def test_shim_scenarios_are_windows_only():
    for s in get_matrix():
        if s.launcher == "pyshim-win":
            assert s.windows_only, f"{s.scenario_id} shim scenario should be windows_only"
