"""Concurrency regression tests found by the round 33 audit.

Each test uses a barrier to maximise overlap and force the race window
open. They are deterministic enough on CI runners — none rely on
``time.sleep`` for synchronisation.
"""
import threading

import pytest

from je_auto_control.utils.remote_desktop.file_sync import FolderSyncEngine
from je_auto_control.utils.rest_api.rest_registry import _RestApiRegistry


@pytest.fixture()
def watch_dir(tmp_path):
    return tmp_path


def _hammer(target, *, threads: int = 8) -> list:
    """Run ``target`` from N threads, all released at once via a barrier.

    Returns the list of exceptions captured per thread (None if the
    thread completed successfully).
    """
    barrier = threading.Barrier(threads)
    errors: list = [None] * threads

    def runner(index):
        barrier.wait()
        try:
            target()
        except Exception as error:  # noqa: BLE001  # pylint: disable=broad-except  # reason: capture-and-assert in test
            errors[index] = error

    workers = [threading.Thread(target=runner, args=(i,)) for i in range(threads)]
    for w in workers:
        w.start()
    for w in workers:
        w.join(timeout=5.0)
    return errors


def test_folder_sync_concurrent_start_does_not_leak_threads(watch_dir):
    """Round 33 bug A: two concurrent start() calls used to race past the
    ``if self._thread is not None`` check and spawn two background
    threads. The second start would overwrite ``_thread``, leaking the
    first.
    """
    engine = FolderSyncEngine(
        watch_dir=watch_dir,
        sender=lambda p, n: None,
        poll_interval_s=0.5,
    )
    sync_threads_before = {t.ident for t in threading.enumerate()
                           if t.name == "folder-sync"}
    try:
        errors = _hammer(engine.start, threads=8)
        assert all(e is None for e in errors), f"errors: {errors}"
        sync_threads_after = {t.ident for t in threading.enumerate()
                              if t.name == "folder-sync"}
        leaked = sync_threads_after - sync_threads_before
        assert len(leaked) <= 1, (
            f"start() spawned {len(leaked)} folder-sync threads — expected at most 1"
        )
    finally:
        engine.stop()


def test_rest_registry_concurrent_start_does_not_leak_servers():
    """Round 33 bug B: ``_RestApiRegistry.start`` constructs and starts
    the new server *outside* the lock. With port=0 the OS hands out a
    fresh ephemeral port to each, so no bind crash — but every
    racing start() spawns its own ``AutoControlREST`` thread, and
    only the one that wins the final ``with self._lock:`` is tracked
    by the registry. The rest leak.

    Detection: count surviving ``AutoControlREST`` threads after the
    hammering. With proper serialisation there should be exactly 1
    (the one the registry tracks). Anything more is a leaked server.
    """
    registry = _RestApiRegistry()

    def attempt_start():
        registry.start(host="127.0.0.1", port=0, enable_audit=False)

    rest_threads_before = {t.ident for t in threading.enumerate()
                           if t.name == "AutoControlREST"}
    try:
        errors = _hammer(attempt_start, threads=4)
        assert all(e is None for e in errors), (
            f"start() raised in some threads: "
            f"{[type(e).__name__ + ': ' + str(e) for e in errors if e]}"
        )
        rest_threads_after = {t.ident for t in threading.enumerate()
                              if t.name == "AutoControlREST"}
        leaked = rest_threads_after - rest_threads_before
        assert len(leaked) == 1, (
            f"start() left {len(leaked)} AutoControlREST threads alive — "
            f"expected exactly 1 (the registry's tracked server)"
        )
    finally:
        registry.stop()
