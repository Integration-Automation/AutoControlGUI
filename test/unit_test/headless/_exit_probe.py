"""Run a GUI probe script in a child interpreter and time how long its exit took.

A probe starts an interpreter and imports PySide6 and the package, which took
up to a minute on a loaded machine: the timeout is for a hung probe, and how
long the exit itself took is measured from the probe's last line, which must
be ``print("exiting", time.time(), flush=True)``.
"""
import os
import subprocess  # nosec B404  # reason: runs the calling test's own probe script
import sys
import time
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[3]
PROBE_TIMEOUT_S = 180


def run_probe(probe: str, mode: str) -> subprocess.CompletedProcess:
    """Run ``probe`` (a literal script) with ``mode`` as its argument."""
    env = dict(os.environ, PYTHONPATH=str(_REPO_ROOT))
    argv = [sys.executable, "-c", probe, mode]   # a literal probe; the tests set mode
    return subprocess.run(argv, env=env, timeout=PROBE_TIMEOUT_S,  # nosec B603  # nosemgrep  # reason: literal argv
                          capture_output=True, text=True, check=False)


def exit_seconds(done: subprocess.CompletedProcess) -> float:
    """Seconds from the probe's ``exiting <epoch>`` line to the process having ended."""
    stamp = done.stdout.strip().splitlines()[-1].split()[-1]
    return time.time() - float(stamp)
