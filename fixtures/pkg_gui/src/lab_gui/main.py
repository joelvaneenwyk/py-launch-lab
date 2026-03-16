"""
GUI entrypoint fixture.

Opens a tiny Tkinter window, waits briefly, then exits.
On non-Windows or headless environments the window step is skipped.
"""

import pathlib
import sys
import tempfile
import time


def run() -> None:
    sentinel = pathlib.Path(tempfile.gettempdir()) / "py_launch_lab_gui.txt"
    sentinel.write_text(f"hello from lab-window-gui\nsys.executable={sys.executable}\n")

    try:
        import tkinter as tk  # noqa: PLC0415

        root = tk.Tk()
        root.title("py-launch-lab GUI fixture")
        root.geometry("200x100")
        root.after(200, root.destroy)  # close after 200 ms
        root.mainloop()
    except Exception:
        # Headless or unavailable — sentinel file is sufficient evidence
        pass

    time.sleep(0.1)
    sys.exit(0)
