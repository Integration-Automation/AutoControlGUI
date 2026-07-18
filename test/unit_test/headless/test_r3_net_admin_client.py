"""Round-3 net audit: the admin address book must persist safely.

``_save`` snapshotted the host map under the lock but wrote the file outside
it, so a stale snapshot could clobber a concurrent add_host (a lost host). The
write itself was truncate-then-write, so a crash mid-write corrupted every
stored token. The fix writes under the lock and atomically (temp + os.replace).
"""
import json
import os
import threading

from je_auto_control.utils.admin.admin_client import AdminConsoleClient


def test_save_writes_under_lock(tmp_path):
    """The file write must happen while ``self._lock`` is held."""
    client = AdminConsoleClient(persist_path=tmp_path / "hosts.json")
    observed: dict = {}
    original = client._write_atomic

    def spy(payload):
        # Non-reentrant Lock: a non-blocking acquire fails iff already held.
        acquired = client._lock.acquire(blocking=False)
        observed["held"] = not acquired
        if acquired:
            client._lock.release()
        return original(payload)

    client._write_atomic = spy
    client.add_host("x", "http://x", "tok")

    assert observed["held"] is True


def test_write_is_atomic_and_cleans_up_on_failure(tmp_path, monkeypatch):
    """A failed replace must leave the prior file intact and drop the temp."""
    path = tmp_path / "hosts.json"
    client = AdminConsoleClient(persist_path=path)
    client.add_host("keep", "http://k", "tok-keep")
    good = path.read_text(encoding="utf-8")

    def boom_replace(_src, _dst):
        raise OSError("disk full")

    monkeypatch.setattr(os, "replace", boom_replace)
    client.add_host("second", "http://s", "tok-2")  # save fails atomically

    assert path.read_text(encoding="utf-8") == good  # not truncated
    data = json.loads(path.read_text(encoding="utf-8"))
    assert {h["label"] for h in data["hosts"]} == {"keep"}
    leftovers = [name for name in os.listdir(tmp_path)
                 if name.startswith(".admin_hosts_")]
    assert leftovers == []  # temp file cleaned up


def test_concurrent_add_host_does_not_lose_hosts(tmp_path):
    """The last save (always a save, under the lock) persists every host."""
    path = tmp_path / "hosts.json"
    client = AdminConsoleClient(persist_path=path)

    def add(index: int) -> None:
        client.add_host(f"host{index}", f"http://h{index}", f"tok{index}")

    threads = [threading.Thread(target=add, args=(i,)) for i in range(20)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    data = json.loads(path.read_text(encoding="utf-8"))
    labels = {h["label"] for h in data["hosts"]}
    assert labels == {f"host{i}" for i in range(20)}
