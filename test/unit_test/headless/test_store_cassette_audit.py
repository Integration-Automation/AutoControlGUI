"""Versioned store, config bundle and HTTP cassette defects (2026-09-24 audit).

The versioned store's high-water marks were not saved, so a deleted key came
back at version 1 after a reload (ABA), and put/delete had no lock; a failed
config-bundle write left the live file moved away; cassettes stored
credentials and ignored unknown or ``headers`` match fields. Fake values only.
"""
import json
import threading

import pytest

from je_auto_control.utils.http_cassette.http_cassette import Cassette, CassetteMissError
from je_auto_control.utils.optimistic.optimistic import VersionConflict, VersionedStore

SECRET = "test-secret-1"


def test_a_recreated_key_does_not_reuse_a_version_after_reload(tmp_path):
    store = VersionedStore()
    store.put("k", "A")
    store.delete("k", expected_version=1)
    path = store.save(str(tmp_path / "store.json"))
    reloaded = VersionedStore.load(path)
    assert reloaded.put("k", "B") == 2
    with pytest.raises(VersionConflict):
        reloaded.put("k", "stale", expected_version=1)


def test_an_older_bare_records_file_still_loads(tmp_path):
    path = tmp_path / "old.json"
    path.write_text(json.dumps({"k": {"value": "A", "version": 3}}), encoding="utf-8")
    assert VersionedStore.load(str(path)).get("k") == {"value": "A", "version": 3}


def test_concurrent_writers_cannot_both_win(monkeypatch):
    store = VersionedStore()
    barrier = threading.Barrier(2, timeout=0.5)
    original = VersionedStore._check

    def slow_check(self, key, expected_version):
        result = original(self, key, expected_version)
        try:
            barrier.wait()
        except threading.BrokenBarrierError:
            pass
        return result

    monkeypatch.setattr(VersionedStore, "_check", slow_check)
    outcomes = []

    def writer(value):
        try:
            outcomes.append(("ok", store.put("k", value, expected_version=0)))
        except VersionConflict:
            outcomes.append(("conflict", value))

    threads = [threading.Thread(target=writer, args=(value,)) for value in ("X", "Y")]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(5)
    assert sorted(kind for kind, _ in outcomes) == ["conflict", "ok"]


def test_a_failed_bundle_write_keeps_the_live_file(tmp_path, monkeypatch):
    from je_auto_control.utils.config_bundle import config_bundle
    target = tmp_path / "admin_hosts.json"
    target.write_text('{"hosts": []}', encoding="utf-8")

    def failing_write(*_args, **_kwargs):
        raise OSError("disk full")

    monkeypatch.setattr(config_bundle, "atomic_write_text", failing_write)
    report = config_bundle.ImportReport()
    config_bundle.ConfigBundleImporter._write_with_backup(
        None, target=target, body="{}", relative="admin_hosts.json", report=report, backup_stamp=1)
    assert target.read_text(encoding="utf-8") == '{"hosts": []}'
    assert report.skipped == ["admin_hosts.json"]


def test_credentials_never_reach_the_cassette(tmp_path):
    cassette = Cassette()
    call = {"method": "GET", "url": "https://api.test/x",
            "headers": {"Authorization": f"Bearer {SECRET}", "Cookie": SECRET, "Accept": "a"}}
    cassette.record(call, {"status": 200, "headers": {"Set-Cookie": SECRET}, "body": "ok"})
    path = cassette.save(str(tmp_path / "c.json"))
    assert SECRET not in open(path, encoding="utf-8").read()
    assert cassette.replay(call)["body"] == "ok"


def test_unknown_match_fields_are_refused_and_headers_are_compared():
    cassette = Cassette()
    cassette.record({"method": "GET", "url": "u", "headers": {"X-Tenant": "A"}}, {"status": 200})
    with pytest.raises(ValueError):
        cassette.replay({"method": "GET", "url": "u"}, match_on=("methd",))
    with pytest.raises(CassetteMissError):
        cassette.replay({"method": "GET", "url": "u", "headers": {"x-tenant": "B"}},
                        match_on=("method", "url", "headers"))
    assert cassette.replay({"method": "GET", "url": "u", "headers": {"x-tenant": "A"}},
                           match_on=("method", "url", "headers"))["status"] == 200
