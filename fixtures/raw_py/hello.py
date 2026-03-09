"""Minimal console script fixture for py-launch-lab."""
import sys
import time

print("hello from raw_py/hello.py", flush=True)
print(f"sys.executable = {sys.executable}", flush=True)
time.sleep(0.1)
sys.exit(0)
