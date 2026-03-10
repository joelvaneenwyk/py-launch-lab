"""
Tests for the ScenarioResult schema (models.py).

These tests validate that the schema is well-formed and that serialisation
round-trips correctly.  They do not require Windows or any external tools.
"""

import json

from launch_lab.models import (
    LauncherKind,
    ProcessInfo,
    ScenarioResult,
    Subsystem,
)


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


def test_minimal_result_is_valid():
    r = _make_result()
    assert r.scenario_id == "test-scenario"
    assert r.platform == "win32"
    assert r.launcher == LauncherKind.PYTHON


def test_subsystem_enum_values():
    assert Subsystem.GUI == "GUI"
    assert Subsystem.CUI == "CUI"
    assert Subsystem.UNKNOWN == "UNKNOWN"
    assert Subsystem.NOT_PE == "NOT_PE"


def test_launcher_kind_enum_values():
    assert LauncherKind.PYTHON == "python"
    assert LauncherKind.PYTHONW == "pythonw"
    assert LauncherKind.UV == "uv"
    assert LauncherKind.UVX == "uvx"


def test_result_json_roundtrip():
    r = _make_result(
        exit_code=0,
        pe_subsystem=Subsystem.CUI,
        stdout_available=True,
        stderr_available=True,
        processes=[ProcessInfo(pid=1234, name="python.exe")],
    )
    serialised = r.model_dump_json()
    data = json.loads(serialised)
    assert data["scenario_id"] == "test-scenario"
    assert data["pe_subsystem"] == "CUI"
    assert data["processes"][0]["pid"] == 1234


def test_result_optional_fields_default_to_none():
    r = _make_result()
    assert r.uv_version is None
    assert r.pe_subsystem is None
    assert r.exit_code is None
    assert r.notes is None


def test_process_info_minimal():
    p = ProcessInfo(pid=42, name="conhost.exe")
    assert p.pid == 42
    assert p.exe is None
