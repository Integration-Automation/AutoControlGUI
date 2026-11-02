"""Bounded, cooperative capture-helper execution; only a newly owned process group may be stopped."""
import contextlib
import os
import signal
import subprocess  # nosec B404  # reason: owned argv-list capture helper, no shell
import sys
import time
from typing import Callable, Optional, cast

from je_auto_control.utils.exception.cancellation import (
    cancellation_checkpoint, cancellation_scope, cancellation_timeout,
)
from je_auto_control.utils.exception.control_signals import raise_caused_run_interruption
from je_auto_control.utils.logging.logging_instance import autocontrol_logger

_REAP_SECONDS = 0.25


def run_capture_helper(argv: list[str], timeout: float) -> subprocess.CompletedProcess[bytes]:
    """Run an explicit capture helper, terminate/reap its group on cancellation or timeout."""
    cancellation_checkpoint()
    # pylint: disable-next=consider-using-with  # reason: Popen.__exit__ waits unboundedly; cleanup below has deadlines
    process = subprocess.Popen(  # nosec B603  # reason: validated capture argv, never a shell
        argv, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        start_new_session=os.name == 'posix', creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0),
    )
    try:
        return _communicate(process, argv, timeout)
    except BaseException as error:  # reason: reap the owned process before propagating the primary control
        _reap_preserving(process, error)
        raise
    finally:
        with cancellation_scope(None):
            _close_streams(process, sys.exc_info()[1])


def _close_streams(process: subprocess.Popen[bytes], primary: Optional[BaseException]) -> None:
    failures = []
    for stream in (process.stdout, process.stderr):
        if stream is not None:
            try:
                stream.close()
            # pylint: disable-next=broad-exception-caught  # reason: close both pipes before preserving controls
            except BaseException as error:  # reason: gather cleanup failures without replacing a pending control
                failures.append(error)
    if not failures:
        return
    if primary is not None:
        raise_caused_run_interruption(primary)
    for failure in failures:
        raise_caused_run_interruption(failure)
    if primary is None:
        raise failures[0]
    autocontrol_logger.debug('capture pipe cleanup failed: %r', failures)


def _communicate(process: subprocess.Popen[bytes], argv: list[str],
                 timeout: float) -> subprocess.CompletedProcess[bytes]:
    deadline = time.monotonic()+max(0.0, timeout)
    while True:
        cancellation_checkpoint()
        remaining = deadline-time.monotonic()
        if remaining <= 0:
            raise subprocess.TimeoutExpired(argv, timeout)
        try:
            stdout, stderr = process.communicate(timeout=cancellation_timeout(remaining))
        except subprocess.TimeoutExpired:
            continue
        if process.returncode:
            raise subprocess.CalledProcessError(process.returncode, argv, output=stdout, stderr=stderr)
        return subprocess.CompletedProcess(argv, process.returncode, stdout, stderr)


def _signal_owned(process: subprocess.Popen[bytes], hard: bool) -> None:
    if process.returncode is not None:
        return  # a reaped child's numeric PID/group may already have been reused
    with contextlib.suppress(ProcessLookupError):
        if os.name == 'posix':
            # Resolve POSIX-only names lazily so the same headless module type-checks on Windows.
            kill_group = cast(Callable[[int, int], None], getattr(os, 'killpg'))
            kill_group(process.pid, int(getattr(signal, 'SIGKILL') if hard else signal.SIGTERM))
        elif process.poll() is None:
            if hard:
                process.kill()
            else:
                process.terminate()


def _reap_preserving(process: subprocess.Popen[bytes], primary: BaseException) -> None:
    try:
        with cancellation_scope(None):
            _signal_owned(process, False)
            try:
                process.communicate(timeout=_REAP_SECONDS)
            except subprocess.TimeoutExpired:
                _signal_owned(process, True)
                process.communicate(timeout=_REAP_SECONDS)
    # pylint: disable-next=broad-exception-caught  # reason: cleanup cannot replace the original task control
    except BaseException as cleanup:  # reason: select original controls after bounded process cleanup
        raise_caused_run_interruption(primary)
        raise_caused_run_interruption(cleanup)
        autocontrol_logger.debug('owned capture process cleanup failed: %r', cleanup)
