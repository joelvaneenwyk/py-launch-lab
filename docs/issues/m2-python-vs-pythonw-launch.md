# Milestone M2 — Direct Python vs PythonW Launch Validation

> Issue: #5 (<https://github.com/joelvaneenwyk/py-launch-lab/issues/5>)

## Description

Implement the process runner and validate the observable differences between launching scripts with `python.exe` (console) and `pythonw.exe` (GUI/no-console). This milestone produces hard evidence of console-window behaviour for each launch mode.

## How it Works

1. `runner.py` spawns child processes with a controlled environment
2. The runner detects whether the spawned process opens a visible console window
3. It inspects the process tree for `conhost.exe` presence
4. Results record `stdout_available`, `stderr_available`, and `visible_window_detected`
5. Evidence artifacts are captured for each scenario

## Tasks

- [ ] Implement `runner.py`: spawn child processes with controlled environment
- [ ] Detect whether spawned process opens a console window
- [ ] Detect `conhost.exe` appearing in process tree
- [ ] Record `stdout_available`, `stderr_available`, `visible_window_detected`
- [ ] Implement integration tests: `test_python_vs_pythonw.py`
- [ ] Capture evidence artifacts for `python script.py` vs `pythonw script.py`

## Related Issues

- Depends on [m1-static-pe-inspection.md](m1-static-pe-inspection.md) - needs PE subsystem classification for result validation

## Next Steps

- [ ] Run comparison tests on a Windows runner
- [ ] Verify evidence artifacts are written to `artifacts/json/`
- [ ] Confirm console-detection logic handles edge cases (e.g., redirected output)
