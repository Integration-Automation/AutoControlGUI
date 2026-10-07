"""Fresh-process GUI startup/memory/first-open and real AC_sleep event-loop benchmarks."""
from __future__ import annotations

import argparse
import json
import math
import os
from pathlib import Path
import platform
import statistics
import subprocess  # nosec B404  # reason: bounded dev-time argv execution without a shell
import sys
import time
import tracemalloc
from typing import Any

# Direct script execution must resolve the benchmark package before selecting a target checkout.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
# CLI package path must precede imports.
from benchmarks.gui_workloads import (  # pylint: disable=wrong-import-position
    catalog_report, percentile95, waiting_script,
)

WORKLOAD = 'main window startup, first Mobile open, Script AC_sleep(.25), QTimer(5ms); tracemalloc'
METRICS = ('startup_ms', 'memory', 'first_open_ms', 'event_loop_p95_ms')


def compare_reports(before: dict[str, Any], after: dict[str, Any]) -> dict[str, object]:
    """Compare only identical environments/workloads; keep lazy first-open tradeoffs visible."""
    if before['environment'] != after['environment']:
        raise ValueError('benchmark environment mismatch')
    if before['workload'] != after['workload']:
        raise ValueError('benchmark workload mismatch')
    comparisons = {}
    for key in METRICS:
        old = statistics.median(run[key] for run in before['runs'])
        new = statistics.median(run[key] for run in after['runs'])
        comparisons[key] = {'before_median': old, 'after_median': new,
                            'ratio': new / old if old else None}
    return {'metrics': comparisons, 'physical_desktop_verified': False}


def check_budgets(before: dict[str, Any], after: dict[str, Any], budget: dict[str, Any]) -> dict[str, object]:
    """Check calibrated medians only on the environment used to establish the limits."""
    comparison = compare_reports(before, after)
    if budget['environment'] != after['environment'] or budget['workload'] != after['workload']:
        raise ValueError('budget calibration environment/workload mismatch')
    checks = {}
    for metric in METRICS:
        limit = budget['limits'][metric]
        old = statistics.median(run[metric] for run in before['runs'])
        new = statistics.median(run[metric] for run in after['runs'])
        observed, maximum = _budget_value(metric, limit, old, new)
        checks[metric] = {'observed': observed, 'maximum': maximum, 'passed': observed <= maximum}
    return {**comparison, 'budget_checks': checks, 'passed': all(check['passed'] for check in checks.values())}


def _budget_value(metric: str, limit: dict[str, Any], old: float, new: float) -> tuple[float, float]:
    """Validate one finite calibration limit and compute its observed value."""
    maximum = limit['maximum']
    if not isinstance(maximum, (int, float)) or not math.isfinite(maximum) or maximum <= 0:
        raise ValueError(f'invalid budget: {metric}')
    kind = limit['kind']
    if kind not in ('ratio', 'absolute') or (kind == 'ratio' and old <= 0):
        raise ValueError(f'invalid budget kind or baseline: {metric}')
    observed = new / old if kind == 'ratio' else new
    return observed, maximum


def _latency(widget: Any, app: Any) -> dict[str, object]:
    from PySide6.QtCore import QTimer  # pylint: disable=import-outside-toplevel  # reason: time imports in the selected fresh checkout
    widget.show_tab('script')
    widget.script_editor.setPlainText(waiting_script(.25))
    widget.script_result_text.clear()
    gaps = []
    previous = time.perf_counter()
    finished_ticks = 0
    timer = QTimer()
    timer.setInterval(5)

    def tick() -> None:
        nonlocal previous, finished_ticks
        now = time.perf_counter()
        gaps.append((now - previous) * 1000)
        previous = now
        if widget.script_result_text.toPlainText():
            finished_ticks += 1

    timer.timeout.connect(tick)  # pylint: disable=no-member  # reason: native Qt signal is bound dynamically
    timer.start()
    QTimer.singleShot(0, widget._execute_manual_script)  # pylint: disable=protected-access  # reason: benchmark the real legacy action
    deadline = time.monotonic() + 10
    while finished_ticks < 4 and time.monotonic() < deadline:
        app.processEvents()
        time.sleep(.001)
    timer.stop()
    if finished_ticks < 4:
        raise RuntimeError('script benchmark did not complete')
    return {'event_loop_p95_ms': percentile95(gaps), 'event_loop_max_ms': max(gaps),
            'event_loop_samples': len(gaps)}


def _child(project_root: Path, fonts: list[str]) -> dict[str, object]:  # pylint: disable=too-many-locals  # reason: all timings share one fresh Qt lifetime
    sys.path.insert(0, str(project_root))
    tracemalloc.start()
    start = time.perf_counter()
    from PySide6 import __version__ as qt_version  # pylint: disable=import-outside-toplevel  # reason: time imports in the selected fresh checkout
    from PySide6.QtCore import QCoreApplication, QEvent  # pylint: disable=import-outside-toplevel  # reason: time imports in the selected fresh checkout
    from PySide6.QtGui import QFontDatabase  # pylint: disable=import-outside-toplevel  # reason: time imports in the selected fresh checkout
    from PySide6.QtWidgets import QApplication  # pylint: disable=import-outside-toplevel  # reason: time imports in the selected fresh checkout
    from je_auto_control.gui.main_window import AutoControlGUIUI  # pylint: disable=import-outside-toplevel  # reason: time imports in the selected fresh checkout
    import je_auto_control  # pylint: disable=import-outside-toplevel  # reason: time imports in the selected fresh checkout
    app = QApplication([])
    families = []
    for font in fonts:
        identifier = QFontDatabase.addApplicationFont(font)
        if identifier < 0:
            raise ValueError(f'font unavailable: {font}')
        families.extend(QFontDatabase.applicationFontFamilies(identifier))
    window = AutoControlGUIUI()
    window.show()
    app.processEvents()
    startup = (time.perf_counter() - start) * 1000
    peak = tracemalloc.get_traced_memory()[1]
    widget = window.auto_control_gui_widget
    catalog = catalog_report(widget)
    start = time.perf_counter()
    widget.show_tab('mobile')
    app.processEvents()
    first_open = (time.perf_counter() - start) * 1000
    latency = _latency(widget, app)
    report = {'environment': {'platform': platform.platform(), 'python': platform.python_version(),
                              'pyside': qt_version, 'qt_platform': app.platformName(),
                              'fonts': sorted(set(families)), 'tracemalloc': True},
              'module_path': str(Path(je_auto_control.__file__).resolve()),
              'startup_ms': startup, 'memory': peak, 'memory_kind': 'tracemalloc_peak_bytes_at_startup',
              'first_open_ms': first_open, **latency, **catalog,
              'physical_desktop_verified': False}
    window.close()
    app.processEvents()
    QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
    tracemalloc.stop()
    return report


def _fresh_run(args: argparse.Namespace) -> dict[str, Any]:
    command = [sys.executable, str(Path(__file__).resolve()), '--child', '--project-root', str(args.project_root)]
    for font in args.font:
        command.extend(['--font', font])
    result = subprocess.run(  # nosec B603  # reason: fixed Python executable and this script; options are separate argv
        command, capture_output=True, text=True, timeout=120,
                            check=False,
                            env=dict(os.environ, PYTHONPATH=str(args.project_root), QT_QPA_PLATFORM='offscreen'))
    if result.returncode:
        raise RuntimeError(result.stderr)
    return json.loads(result.stdout)


def _arguments() -> argparse.Namespace:
    """Run fresh subprocess samples or compare already saved matching reports."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--project-root', type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument('--font', action='append', default=[])
    parser.add_argument('--runs', type=int, default=3)
    parser.add_argument('--warmup', type=int, default=1)
    parser.add_argument('--output', type=Path)
    parser.add_argument('--compare', nargs=2, type=Path)
    parser.add_argument('--budget', type=Path, help='Calibrated limits; requires --compare; fails if exceeded')
    parser.add_argument('--child', action='store_true')
    return parser.parse_args()

def _run_report(args: argparse.Namespace) -> dict[str, Any]:
    """Collect bounded fresh samples and record the target source revision."""
    if not 1 <= args.runs <= 10 or not 0 <= args.warmup <= 3:
        raise ValueError('--runs must be 1–10 and --warmup 0–3')
    warmups = [_fresh_run(args) for _ in range(args.warmup)]
    runs = [_fresh_run(args) for _ in range(args.runs)]
    revision = subprocess.run(  # nosec B603 B607  # reason: fixed read-only git argv in developer-selected checkout
        ['git', 'rev-parse', 'HEAD'], cwd=args.project_root,
                              capture_output=True, text=True, timeout=10, check=True).stdout.strip()
    report = {'workload': WORKLOAD + f'; warmup={args.warmup}', 'source_revision': revision,
              'environment': runs[0]['environment'], 'warmup_runs': warmups, 'runs': runs}
    if any(run['environment'] != report['environment'] for run in runs):
        raise ValueError('sample environments differ')
    return report

def _report(args: argparse.Namespace) -> dict[str, Any]:
    """Select saved-report comparison or live fresh-process measurement."""
    args.project_root = args.project_root.resolve()
    if args.compare:
        reports = [json.loads(path.read_text(encoding='utf-8')) for path in args.compare]
        return (check_budgets(reports[0], reports[1], json.loads(args.budget.read_text(encoding='utf-8')))
                  if args.budget else compare_reports(*reports))
    return _run_report(args)

def main() -> None:
    """Run fresh samples or check saved reports against calibrated limits."""
    args = _arguments()
    if args.budget and not args.compare:
        raise ValueError('--budget requires --compare')
    if args.child:
        print(json.dumps(_child(args.project_root.resolve(), args.font)))
        return
    report = _report(args)
    output = json.dumps(report, indent=2) + '\n'
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(output, encoding='utf-8')
    else:
        print(output, end='')
    if args.budget and not report['passed']:
        raise SystemExit(1)


if __name__ == '__main__':
    main()
