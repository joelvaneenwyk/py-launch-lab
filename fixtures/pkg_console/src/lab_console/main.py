"""Console entrypoint fixture."""

import sys
import time


def run() -> None:
    print("hello from lab-console", flush=True)
    print(f"sys.executable = {sys.executable}", flush=True)
    time.sleep(0.1)
    sys.exit(0)
