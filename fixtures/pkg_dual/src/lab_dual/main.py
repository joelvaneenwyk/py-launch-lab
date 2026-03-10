"""
Dual-mode fixture: exposes both a console and a GUI entrypoint.

Both entrypoints call shared logic and differ only in how they report results.
"""

import pathlib
import sys
import tempfile
import time


def _shared_work() -> str:
    return f"sys.executable={sys.executable}"


def run_console() -> None:
    print("hello from lab-dual-console", flush=True)
    print(_shared_work(), flush=True)
    time.sleep(0.1)
    sys.exit(0)


def run_gui() -> None:
    sentinel = pathlib.Path(tempfile.gettempdir()) / "py_launch_lab_dual_gui.txt"
    sentinel.write_text(f"hello from lab-dual-gui\n{_shared_work()}\n")
    time.sleep(0.1)
    sys.exit(0)
