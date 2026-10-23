"""Durable background dispatch defers busy targets without consuming application retries."""
import pytest

from je_auto_control.utils.exception.exceptions import AutoControlException
from je_auto_control.utils.work_queue.work_queue import WorkQueue


def test_busy_target_deferral_preserves_retry_budget_and_fences_old_claim(tmp_path):
    queue = WorkQueue(str(tmp_path / "queue.sqlite"), "agent")
    identifier = queue.add({"task_id": "one"})
    first = queue.get_next()
    queue.defer(identifier, claim=first.claim)
    second = queue.get_next()
    assert second.retries == 0
    assert second.claim > first.claim
    with pytest.raises(AutoControlException):
        queue.defer(identifier, claim=first.claim)
    queue.complete(identifier, claim=second.claim)
