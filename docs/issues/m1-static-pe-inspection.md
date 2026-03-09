# Milestone M1 — Static PE Inspection

> Issue: TBD

## Description

Implement static PE header inspection so the project can classify any Windows executable as GUI-subsystem or console-subsystem. This is the foundational analysis layer that all later milestones depend on.

## How it Works

1. Read the PE (Portable Executable) header from a given `.exe` file
2. Extract the `IMAGE_SUBSYSTEM` field from the optional header
3. Classify the executable as `IMAGE_SUBSYSTEM_WINDOWS_GUI` or `IMAGE_SUBSYSTEM_WINDOWS_CUI`
4. Store the result in a `pe_subsystem` field on the scenario result object

## Tasks

- [ ] Implement `inspect_pe.py`: read PE header from any Windows EXE
- [ ] Classify `IMAGE_SUBSYSTEM_WINDOWS_GUI` vs `IMAGE_SUBSYSTEM_WINDOWS_CUI`
- [ ] Support inspection of Python, PythonW, uv, uvw executables
- [ ] Store `pe_subsystem` field in result objects
- [ ] Unit tests for PE inspection against known executables

## Next Steps

- [ ] Verify PE parsing against CPython `python.exe` and `pythonw.exe`
- [ ] Confirm `uv` and `uvw` executables are correctly classified
- [ ] Ensure graceful handling on non-Windows platforms
