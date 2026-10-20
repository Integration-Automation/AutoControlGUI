"""Demonstrate scoped cancellation; --active explicitly runs system checks and may request capture consent."""
import argparse
from concurrent.futures import CancelledError
from dataclasses import asdict
import json
import math
from threading import Timer, TIMEOUT_MAX
from typing import Optional

from je_auto_control.api import CancellationToken, TaskProgress, cancellation_scope, run_diagnostics


def _demo() -> dict[str, object]:
    progress: list[TaskProgress] = []
    token = CancellationToken(1, progress.append)
    status = 'completed'
    try:
        with cancellation_scope(token):
            token.report(0, 2, 'controlled example')
            token.cancel()
            token.checkpoint()
    except CancelledError:
        status = 'cancelled'
    return {'mode': 'demo', 'status': status, 'progress': [asdict(item) for item in progress]}


def _active(cancel_after: Optional[float]) -> dict[str, object]:
    token = CancellationToken(1)
    timer = Timer(cancel_after, token.cancel) if cancel_after is not None else None
    if timer is not None:
        timer.daemon = True
        timer.start()
    try:
        with cancellation_scope(token):
            report = run_diagnostics()
        return {'mode': 'active', 'status': 'completed', 'report': report.to_dict(), 'has_errors': report.has_errors}
    except (CancelledError, KeyboardInterrupt):
        return {'mode': 'active', 'status': 'cancelled'}
    finally:
        if timer is not None:
            timer.cancel()
            timer.join(1)


def main(argv: Optional[list[str]] = None) -> int:
    """Run a controlled demo, or explicit active checks with an optional cooperative stop timer."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--active', action='store_true', help='Run actual diagnostics, including screen capture')
    parser.add_argument('--cancel-after', type=float, help='Request cooperative stop after this many seconds')
    args = parser.parse_args(argv)
    interval: Optional[float] = args.cancel_after
    if interval is not None:
        if not args.active or not math.isfinite(interval) or not 0 <= interval <= TIMEOUT_MAX:
            parser.error('--cancel-after requires --active and a finite nonnegative supported interval')
    result = _active(interval) if args.active else _demo()
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return int(bool(result.get('has_errors', False)))


if __name__ == '__main__':
    raise SystemExit(main())
