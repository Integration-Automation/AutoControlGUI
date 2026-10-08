"""How long the GUI takes to start, and what it costs in memory, from a cold interpreter.

    python benchmarks/gui_startup.py --runs 5 --output after.json
    python benchmarks/gui_startup.py --compare before.json after.json

Each run is a new child interpreter, so imports are paid every time. The
window is built and painted on the ``offscreen`` platform plugin: nothing
appears on the desktop, and the user's GUI settings are neither read nor
written. ``startup_ms`` is from the first line of the child to the first
painted frame; ``process_ms`` adds starting and stopping the interpreter.
"""
import argparse
import json
import os
import subprocess  # nosec B404  # reason: starts this script's own child with a fixed argv
import sys
import time
from typing import Any, Dict, List, Optional

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import _gui_bench as bench  # noqa: E402

WORKLOAD = "main window, default tabs, first frame"


def measure_once() -> Dict[str, Any]:
    """Start the GUI in this process and return its timings (the child side)."""
    start = time.perf_counter()
    bench.prepare_process()
    from PySide6.QtWidgets import QApplication
    qt_imported = time.perf_counter()
    from je_auto_control.gui.main_window import AutoControlGUIUI
    from je_auto_control.gui.theme import prepare_application
    imported = time.perf_counter()
    app = QApplication.instance() or QApplication([])
    prepare_application(app)
    window = AutoControlGUIUI()
    built = time.perf_counter()
    window.show()
    app.processEvents()
    window.grab()
    painted = time.perf_counter()
    entries = window.auto_control_gui_widget._tab_entries  # noqa: SLF001  # reason: counting built tabs
    return {
        "startup_ms": (painted - start) * 1000,
        "phases_ms": {"import_qt": (qt_imported - start) * 1000, "import_gui": (imported - qt_imported) * 1000,
                      "build_window": (built - imported) * 1000, "first_frame": (painted - built) * 1000},
        "memory": {"rss_mb": bench.rss_mb()},
        "tabs_built": sum(1 for entry in entries if entry.built),
        "tabs_registered": len(entries),
        "modules_loaded": sum(1 for name in sys.modules if name.startswith("je_auto_control")),
        "environment": bench.environment(app),
    }


def _child() -> None:
    sys.stdout.write(json.dumps(measure_once()))
    sys.stdout.flush()
    # Some tabs start helper threads when built; the numbers are out, so skip teardown.
    os._exit(0)


def _run_child() -> Dict[str, Any]:
    env = dict(os.environ)
    env.setdefault("QT_QPA_PLATFORM", "offscreen")
    env[bench.SETTINGS_ENV] = "off"
    start = time.perf_counter()
    argv = [sys.executable, os.path.abspath(__file__), "--child"]
    done = subprocess.run(argv,  # nosec B603  # nosemgrep  # reason: this file, this interpreter
                          capture_output=True, text=True, env=env, timeout=300, check=False)
    elapsed = (time.perf_counter() - start) * 1000
    if done.returncode != 0:
        raise SystemExit(f"benchmark child failed ({done.returncode}):\n{done.stderr[-2000:]}")
    result: Dict[str, Any] = json.loads(done.stdout)
    result["process_ms"] = elapsed
    return result


def run(runs: int) -> Dict[str, Any]:
    """Start the GUI ``runs`` times in child interpreters and summarise."""
    results = [_run_child() for _ in range(max(runs, 1))]
    phases = results[0]["phases_ms"]
    memory = [r["memory"]["rss_mb"] for r in results if r["memory"]["rss_mb"] is not None]
    return {
        "benchmark": "gui_startup",
        "workload": WORKLOAD,
        "runs": len(results),
        "environment": results[0]["environment"],
        "startup_ms": bench.summary(r["startup_ms"] for r in results),
        "process_ms": bench.summary(r["process_ms"] for r in results),
        "phases_ms": {name: bench.summary(r["phases_ms"][name] for r in results) for name in phases},
        "memory": {"rss_mb": bench.summary(memory)},
        "tabs_built": results[0]["tabs_built"],
        "tabs_registered": results[0]["tabs_registered"],
        "modules_loaded": results[0]["modules_loaded"],
    }


def main(argv: Optional[List[str]] = None) -> int:
    """Command line entry point."""
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--runs", type=int, default=5, help="cold starts to measure (default 5)")
    parser.add_argument("--output", help="write the JSON report here instead of stdout")
    parser.add_argument("--compare", nargs=2, metavar=("BEFORE", "AFTER"), help="compare two saved reports")
    parser.add_argument("--child", action="store_true", help=argparse.SUPPRESS)
    args = parser.parse_args(argv)
    if args.child:
        _child()
    if args.compare:
        bench.emit(bench.compare(bench.load(args.compare[0]), bench.load(args.compare[1])), args.output)
        return 0
    bench.emit(run(args.runs), args.output)
    return 0


if __name__ == "__main__":
    sys.exit(main())
