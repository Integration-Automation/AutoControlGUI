"""Cooperative cancellation and immutable progress do not depend on Qt or native backends."""
from concurrent.futures import CancelledError
from dataclasses import FrozenInstanceError
import os
from pathlib import Path
import subprocess
import sys
import threading

import pytest

from je_auto_control.utils.exception.cancellation import CancellationToken


def test_token_cancel_wakes_its_waiter_and_stops_further_progress():
    observations = []
    token = CancellationToken(7, observations.append)
    token.report(1, 3, 'controlled')
    progress, = observations
    assert (progress.task_id, progress.completed, progress.total, progress.detail) == (7, 1, 3, 'controlled')
    with pytest.raises(FrozenInstanceError):
        progress.completed = 2
    entered, woke = threading.Event(), threading.Event()

    def waiter():
        entered.set()
        if token.wait(3):
            woke.set()

    thread = threading.Thread(target=waiter)
    thread.start()
    assert entered.wait(1)
    token.cancel()
    thread.join(1)
    assert not thread.is_alive() and woke.is_set() and token.is_cancelled
    with pytest.raises(CancelledError):
        token.checkpoint()
    with pytest.raises(CancelledError):
        token.report(2, 3)
    assert observations == [progress] and token.wait(0)


@pytest.mark.parametrize('timeout', [-1, float('inf'), float('-inf'), float('nan'), 1e308])
def test_wait_refuses_unbounded_or_negative_intervals(timeout):
    with pytest.raises(ValueError, match='finite nonnegative'):
        CancellationToken(1).wait(timeout)


@pytest.mark.parametrize('completed', [-1, True, 1.5, '1'])
def test_invalid_completed_counts_are_rejected_before_notifying(completed):
    observations = []
    with pytest.raises(ValueError, match='nonnegative integer'):
        CancellationToken(1, observations.append).report(completed)
    assert observations == []


@pytest.mark.parametrize('total', [-1, True, 0, 1.5, '3'])
def test_invalid_totals_are_rejected_before_notifying(total):
    observations = []
    with pytest.raises(ValueError, match='at least as large'):
        CancellationToken(1, observations.append).report(1, total)
    assert observations == []


def test_progress_details_need_text_and_a_callback_is_optional():
    token = CancellationToken(1)
    token.report(0)
    assert not token.wait(0) and not token.is_cancelled
    with pytest.raises(TypeError, match='must be text'):
        token.report(1, detail=7)


def test_cancellation_primitives_import_without_qt_in_a_fresh_interpreter():
    root = Path(__file__).resolve().parents[3]
    code = ('import sys;sys.path.insert(0,sys.argv[1]);'
            'from je_auto_control.utils.exception.cancellation import CancellationToken;'
            'assert not any(name.startswith("PySide6") for name in sys.modules);'
            'token=CancellationToken(1);token.cancel();assert token.is_cancelled')
    result = subprocess.run([sys.executable, '-I', '-c', code, str(root)], check=False,
                            capture_output=True, text=True, timeout=30, env=os.environ.copy())
    assert result.returncode == 0, result.stderr
