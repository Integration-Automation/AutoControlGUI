"""Immediate stop requests cannot overwrite or reject concurrently committed verified completion."""
import threading
from concurrent.futures import ThreadPoolExecutor

import pytest

from .test_agent_runtime import managed as managed, specification


@pytest.mark.parametrize("operation", ["pause", "cancel"])
def test_completion_between_stop_read_and_write_preserves_terminal_evidence(managed, monkeypatch, operation):
    runtime, target = managed
    task = runtime.submit(specification())
    frame = runtime.observe(task.task_id)
    runtime.act(task.task_id, {"tool": "AC_increment", "observation_id": frame.observation_id})
    read, published = threading.Event(), threading.Event()
    requesting = {}
    original = runtime._row

    def interleaved_row(identifier):
        row = original(identifier)
        if threading.get_ident() == requesting.get("thread") and not read.is_set():
            read.set()
            assert published.wait(5)
        return row

    def stop_after_read():
        requesting["thread"] = threading.get_ident()
        return getattr(runtime, operation)(task.task_id)

    monkeypatch.setattr(runtime, "_row", interleaved_row)
    with ThreadPoolExecutor(max_workers=1) as worker:
        pending = worker.submit(stop_after_read)
        try:
            assert read.wait(5)
            completed = runtime.finish(task.task_id)
            assert completed.state == "succeeded"
        finally:
            published.set()
        result = pending.result(timeout=5)
    assert result.state == "succeeded" and result.verification == completed.verification
    assert result.metadata["input_released"] is True and target.calls == ["AC_increment"]
