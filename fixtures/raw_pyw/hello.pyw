"""Minimal GUI-mode script fixture for py-launch-lab (no console output)."""

import pathlib
import sys
import tempfile
import time

# NOTE: stdout may not be available in pythonw / GUI mode.
# Write to a temp file instead so the test runner can verify execution.
sentinel = pathlib.Path(tempfile.gettempdir()) / "py_launch_lab_raw_pyw.txt"
sentinel.write_text(f"hello from raw_pyw/hello.pyw\nsys.executable={sys.executable}\n")
time.sleep(0.1)
sys.exit(0)
