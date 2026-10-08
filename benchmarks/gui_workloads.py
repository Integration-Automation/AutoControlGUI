"""What using the GUI costs: first open of each tab, switching, searching, and how long the event loop stalls.

    python benchmarks/gui_workloads.py --output after.json
    python benchmarks/gui_workloads.py --tabs record,variables,scheduler
    python benchmarks/gui_workloads.py --compare before.json after.json

One process, the ``offscreen`` platform plugin, the user's GUI settings left
alone. Every step runs from the event loop while a 5 ms timer ticks; how late
each tick arrives is the stall a user would feel, and ``event_loop_p95_ms`` is
its 95th percentile over the whole workload. ``idle_event_loop_p95_ms`` is the
same with every opened tab left running and nothing else happening.
"""
import argparse
import os
import sys
import time
from typing import Any, Callable, Dict, List, Optional

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import _gui_bench as bench  # noqa: E402

TICK_MS = 5
IDLE_MS = 500
SEARCHES = ("rec", "script", "usb", "remote desktop", "zzz", "")


class _Ticker:
    """Records how late each timer tick arrives."""

    def __init__(self, timer_type: Any) -> None:
        self.late_ms: List[float] = []
        self._last = time.perf_counter()
        self.timer = timer_type()
        self.timer.setInterval(TICK_MS)
        self.timer.timeout.connect(self._tick)

    def _tick(self) -> None:
        now = time.perf_counter()
        self.late_ms.append(max((now - self._last) * 1000 - TICK_MS, 0.0))
        self._last = now

    def restart(self) -> List[float]:
        """Return the samples so far and start a new series."""
        taken, self.late_ms = self.late_ms, []
        self._last = time.perf_counter()
        return taken


def _timed(step: Callable[[], Any], app: Any) -> float:
    start = time.perf_counter()
    step()
    app.processEvents()
    return (time.perf_counter() - start) * 1000


def _steps(window: Any, keys: List[str], app: Any, results: Dict[str, Any]) -> List[Callable[[], None]]:
    workspace, navigation = window.auto_control_gui_widget, window.navigation
    first_open: Dict[str, float] = results.setdefault("first_open_ms", {})
    switch: List[float] = results.setdefault("_switch", [])
    search: List[float] = results.setdefault("_search", [])
    theme: List[float] = results.setdefault("_theme", [])
    steps: List[Callable[[], None]] = []
    for key in keys:
        steps.append(lambda key=key: first_open.__setitem__(
            key, round(_timed(lambda: workspace.activate_tab(key), app), 1)))
    for key in keys:
        steps.append(lambda key=key: switch.append(_timed(lambda: workspace.activate_tab(key), app)))
    for text in SEARCHES:
        steps.append(lambda text=text: search.append(_timed(lambda: navigation.search.setText(text), app)))
    for name in ("light", "dark"):
        steps.append(lambda name=name: theme.append(_timed(lambda: window.set_theme(name), app)))
    return steps


def run(tabs: Optional[List[str]] = None) -> Dict[str, Any]:
    """Drive the workload in this process and return the report."""
    bench.prepare_process()
    from PySide6.QtCore import QTimer
    from PySide6.QtWidgets import QApplication

    from je_auto_control.gui.main_window import AutoControlGUIUI
    from je_auto_control.gui.theme import prepare_application
    app = QApplication.instance() or QApplication([])
    prepare_application(app)
    window = AutoControlGUIUI()
    window.show()
    app.processEvents()
    registered = [row["key"] for row in window.auto_control_gui_widget.list_registered_tabs()]
    keys = [key for key in (tabs or registered) if key in registered]
    results: Dict[str, Any] = {}
    steps = _steps(window, keys, app, results)
    ticker = _Ticker(QTimer)
    driver = QTimer()
    driver.setInterval(0)

    def advance() -> None:
        if steps:
            steps.pop(0)()
            return
        driver.stop()
        results["_work"] = ticker.restart()
        QTimer.singleShot(IDLE_MS, app.quit)

    driver.timeout.connect(advance)
    ticker.timer.start()
    driver.start()
    app.exec()
    idle = ticker.restart()
    work = results.pop("_work", [])
    opened = list(results["first_open_ms"].values())
    return {
        "benchmark": "gui_workloads",
        "workload": "open, revisit, search, theme: " + ",".join(keys),
        "environment": bench.environment(app),
        "tabs_opened": len(keys),
        "first_open_ms": results["first_open_ms"],
        "first_open_summary_ms": {"median": bench.percentile(opened, 50), "p95": bench.percentile(opened, 95),
                                  "max": max(opened, default=0.0), "total": round(sum(opened), 1)},
        "switch_ms": bench.summary(results.pop("_switch")),
        "search_ms": bench.summary(results.pop("_search")),
        "theme_switch_ms": bench.summary(results.pop("_theme")),
        "event_loop_p95_ms": round(bench.percentile(work, 95), 1),
        "event_loop_max_ms": round(max(work, default=0.0), 1),
        "event_loop_ticks": len(work),
        "idle_event_loop_p95_ms": round(bench.percentile(idle, 95), 1),
        "memory": {"rss_mb": bench.rss_mb()},
    }


def main(argv: Optional[List[str]] = None) -> int:
    """Command line entry point."""
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--tabs", help="comma-separated tab keys (default: every registered tab)")
    parser.add_argument("--output", help="write the JSON report here instead of stdout")
    parser.add_argument("--compare", nargs=2, metavar=("BEFORE", "AFTER"), help="compare two saved reports")
    args = parser.parse_args(argv)
    if args.compare:
        bench.emit(bench.compare(bench.load(args.compare[0]), bench.load(args.compare[1])), args.output)
        return 0
    tabs = [key.strip() for key in args.tabs.split(",") if key.strip()] if args.tabs else None
    bench.emit(run(tabs), args.output)
    # Tabs opened here started timers and helper threads; the report is out, so skip teardown
    # once the workers have finished what they were doing.
    from PySide6.QtWidgets import QApplication
    bench.wait_for_workers(QApplication.instance())
    os._exit(0)


if __name__ == "__main__":
    sys.exit(main())
