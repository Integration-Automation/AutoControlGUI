"""Stores sharing a JSON file across processes must not overwrite each other.

The approval gate, the asset store and the locator-repair store each loaded
their file once and wrote back their own copy on every change: two checkers
deciding one request were both told they had succeeded, and an asset or a
suggestion added by another process vanished on the next write. Separate
instances stand in for separate processes here -- each used to hold its own
copy exactly as a process does.
"""
import os
import threading
import time

import pytest

from je_auto_control.utils.assets.assets import AssetStore
from je_auto_control.utils.governance.governance import ApprovalGate
from je_auto_control.utils.json_store import json_store
from je_auto_control.utils.locator_repair.locator_repair import RepairStore


def test_a_request_is_decided_only_once(tmp_path):
    path = str(tmp_path / "gate.json")
    token = ApprovalGate(path).request("deploy", requester="maker")
    first, second = ApprovalGate(path), ApprovalGate(path)   # both loaded while pending
    assert first.approve(token, "checker-a") is True
    assert second.reject(token, "checker-b") is False
    assert ApprovalGate(path).status(token) == "approved"


def test_a_checker_sees_a_decision_made_elsewhere(tmp_path):
    path = str(tmp_path / "gate.json")
    maker = ApprovalGate(path)
    token = maker.request("deploy", requester="maker")
    ApprovalGate(path).approve(token, "checker")
    assert maker.is_approved(token)


def test_assets_added_by_two_stores_both_survive(tmp_path):
    path = str(tmp_path / "assets.json")
    first, second = AssetStore(path), AssetStore(path)
    first.set("a", 1)
    second.set("b", 2)
    names = {asset.name for asset in AssetStore(path).list()}
    assert names == {"a", "b"}


def test_suggestions_recorded_by_two_stores_both_survive(tmp_path):
    path = str(tmp_path / "repair.json")
    first, second = RepairStore(path), RepairStore(path)
    first.record("k1", method="image", confidence=0.5)
    second.record("k2", method="image", confidence=0.5)
    assert {item["key"] for item in RepairStore(path).pending()} == {"k1", "k2"}


def test_concurrent_updates_are_all_kept(tmp_path):
    path = str(tmp_path / "assets.json")
    threads = [threading.Thread(target=lambda n=n: AssetStore(path).set(f"n{n}", n))
               for n in range(20)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    assert len(AssetStore(path).list()) == 20


def test_a_lock_left_by_a_dead_process_is_taken_over(tmp_path, monkeypatch):
    target = tmp_path / "gate.json"
    lock = tmp_path / "gate.json.lock"
    lock.write_text("", encoding="utf-8")
    old = time.time() - 3600
    os.utime(lock, (old, old))
    ApprovalGate(str(target)).request("deploy")
    assert not lock.exists()


def test_a_held_lock_times_out(tmp_path, monkeypatch):
    monkeypatch.setattr(json_store, "_LOCK_WAIT_S", 0.05)
    (tmp_path / "gate.json.lock").write_text("", encoding="utf-8")
    with pytest.raises(TimeoutError):
        ApprovalGate(str(tmp_path / "gate.json")).request("deploy")


def test_without_a_path_the_state_stays_in_memory():
    gate = ApprovalGate()
    token = gate.request("deploy", requester="maker")
    assert gate.approve(token, "checker") and gate.is_approved(token)
