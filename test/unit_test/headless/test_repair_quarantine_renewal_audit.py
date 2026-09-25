"""Repair commands without a db, artifacts, shared quarantine files, renewals, NumPy bboxes, plugins, timelines.

Without ``db`` every repair command built a fresh in-memory store, so nothing
recorded was ever resolved; numbers and lists became the wrong artifact bytes;
two quarantine stores on one file overwrote each other; a zero or NaN renewal
interval spun certbot and a restart ran two renewals at once; force mode
raised on a NumPy bbox and trial mode answered NumPy points; a plugin whose
import raised escaped; NaN and negative step durations reached the timeline.
"""
import json
import threading
import time

import numpy as np
import pytest


def test_repair_commands_share_one_store_without_a_db():
    from je_auto_control.utils.executor.action_executor import Executor
    executor = Executor()
    executor.execute_action([["AC_repair_record", {"key": "audit-login", "method": "vlm",
                                                   "coordinates": [3, 4], "confidence": "0.95"}]])
    record = executor.execute_action([["AC_repair_resolved", {"key": "audit-login"}]])
    assert list(record.values())[0]["locator"]["coordinates"] == [3, 4]
    from je_auto_control.utils.mcp_server.tools._handlers_locators import repair_pending, repair_record
    suggestion = repair_record("audit-save", "img", confidence=0.1)
    assert suggestion["id"] in {row["id"] for row in repair_pending()["pending"]}


def test_a_hand_edited_repair_file_is_read_around(tmp_path):
    from je_auto_control.utils.locator_repair import RepairStore
    path = tmp_path / "repairs.json"
    path.write_text(json.dumps({"suggestions": [{"key": "k"}, 5, {"id": "x", "key": "k", "status": "applied",
                                                                  "method": "m"}]}), encoding="utf-8")
    store = RepairStore(str(path))
    assert store.resolved("k")["method"] == "m"
    assert store.approve("missing") is False
    path.write_text(json.dumps({"suggestions": {"a": 1}}), encoding="utf-8")
    assert store.record("k", method="m").status == "applied"


@pytest.mark.parametrize("content, expected", [
    (3, b"3"), ([104, 105], b"[\n  104,\n  105\n]"), ({"b": 1, "a": 2}, b'{\n  "a": 2,\n  "b": 1\n}'),
    ("text", b"text"), (b"\x00raw", b"\x00raw"),
])
def test_artifacts_store_the_value_they_were_given(content, expected, tmp_path):
    from je_auto_control.utils.approval import verify_artifact
    result = verify_artifact("artifact", content, str(tmp_path))
    with open(result.received_path, "rb") as received:
        assert received.read() == expected


def test_pending_artifacts_lists_a_name_once(tmp_path):
    from je_auto_control.utils.approval import pending_artifacts, verify_artifact
    verify_artifact("dup", "a", str(tmp_path), extension="txt")
    verify_artifact("dup", "b", str(tmp_path), extension="json")
    assert pending_artifacts(str(tmp_path)) == ["dup"]


def test_two_quarantine_stores_on_one_file_keep_each_others_names(tmp_path):
    from je_auto_control.utils.quarantine import QuarantineStore
    path = tmp_path / "quarantine.json"
    runner, cli = QuarantineStore(path), QuarantineStore(path)
    cli.add("flaky_login")
    runner.add("flaky_upload")
    assert runner.is_quarantined("flaky_login")
    assert QuarantineStore(path).names() == {"flaky_login", "flaky_upload"}
    assert cli.remove("flaky_upload") and runner.names() == {"flaky_login"}
    assert runner.clear() == 1 and cli.names() == set()


@pytest.mark.parametrize("interval", [0, -5, float("nan"), float("inf")])
def test_a_renewal_interval_must_be_positive_and_finite(interval):
    from je_auto_control.utils.tls_acme import RenewalScheduler
    with pytest.raises(ValueError):
        RenewalScheduler("no_such.pem", lambda: None, check_interval_s=interval)


def test_a_restart_during_a_renewal_does_not_run_two(tmp_path):
    from je_auto_control.utils.tls_acme import RenewalScheduler
    active, peak, lock, release = [0], [0], threading.Lock(), threading.Event()

    def renew():
        with lock:
            active[0] += 1
            peak[0] = max(peak[0], active[0])
        release.wait(2)
        with lock:
            active[0] -= 1

    scheduler = RenewalScheduler(str(tmp_path / "missing.pem"), renew, check_interval_s=3600)
    scheduler.start()
    deadline = time.monotonic() + 2
    while active[0] == 0 and time.monotonic() < deadline:
        time.sleep(0.01)
    scheduler.stop(timeout=0.05)          # renew() still running
    scheduler.start()
    time.sleep(0.1)
    release.set()
    scheduler.stop(timeout=2)
    assert peak[0] == 1


def test_force_mode_takes_a_numpy_bbox_and_points_are_plain_ints():
    from je_auto_control.utils.act_modes import act_with_mode
    from je_auto_control.utils.actionability.actionability import GateConfig
    bbox = np.array([10, 20, 30, 40])
    forced = act_with_mode(lambda point: point, lambda: bbox, mode="force")
    trial = act_with_mode(lambda point: point, lambda: bbox, mode="trial",
                          config=GateConfig(timeout_s=0.0, stable_for_s=0.0))
    assert forced["point"] == [25, 40]
    json.dumps(forced)
    json.dumps(trial)


def test_a_plugin_whose_import_raises_is_reported_not_raised(tmp_path, monkeypatch):
    from je_auto_control.utils.package_manager.package_manager_class import PackageManager
    (tmp_path / "audit_bad_plugin.py").write_text('raise RuntimeError("missing config")\n', encoding="utf-8")
    monkeypatch.syspath_prepend(str(tmp_path))
    manager = PackageManager()
    assert manager.check_package("audit_bad_plugin") is None
    assert manager.check_package("__main__") is None     # find_spec raised ValueError
    target = type("Target", (), {"event_dict": {}})()
    manager.add_package_to_target("audit_bad_plugin", target)
    assert target.event_dict == {}


@pytest.mark.parametrize("duration", [float("nan"), float("inf"), -3.0])
def test_a_timeline_refuses_bad_durations(duration):
    from je_auto_control.utils.step_timeline import build_timeline
    with pytest.raises(ValueError, match="step 1"):
        build_timeline([{"name": "a", "duration": 1.0}, {"name": "b", "duration": duration}])
