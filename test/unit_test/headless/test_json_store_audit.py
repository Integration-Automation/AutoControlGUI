"""Regression tests for the JSON-file store defects of the 2026-09-23 audit.

Four stores rewrote their file in place, so a concurrent reader saw it half
written, and a file that was valid JSON of the wrong shape or not UTF-8 crashed
their constructors. The A/B locator store marked itself loaded before reading,
so one failed read led to every stored count being overwritten, and the
JSON-lines logs appended onto a torn last line and lost the new record too.
"""
import json
from pathlib import Path

import pytest

from je_auto_control.utils.ab_locator.store import ABStore
from je_auto_control.utils.json_store.json_store import append_json_line
from je_auto_control.utils.quarantine import store as quarantine_store
from je_auto_control.utils.rbac import users
from je_auto_control.utils.remote_desktop import fingerprint, trust_list


@pytest.mark.parametrize("content", [b"[1, 2]", b"\xff\xfe not utf-8", b'{"entries": 5}'])
def test_a_malformed_quarantine_file_loads_empty(tmp_path, content):
    path = tmp_path / "quarantine.json"
    path.write_bytes(content)
    assert quarantine_store.QuarantineStore(path).list() == []


@pytest.mark.parametrize("build", [
    lambda path: trust_list.TrustList(path).list_entries(),
    lambda path: fingerprint.KnownHosts(path).list_entries(),
    lambda path: users.UserStore(path).list_users(),
], ids=["trust-list", "known-hosts", "users"])
def test_a_file_that_is_not_utf8_loads_empty(tmp_path, build):
    path = tmp_path / "store.json"
    path.write_bytes(b"\xff\xfe not utf-8")
    assert not build(path)


@pytest.mark.parametrize("module, save", [
    (quarantine_store, lambda path: quarantine_store.QuarantineStore(path).add("t1")),
    (trust_list, lambda path: trust_list.TrustList(path).add("viewer-1")),
    (fingerprint, lambda path: fingerprint.KnownHosts(path).remember("host", "ab" * 32)),
], ids=["quarantine", "trust-list", "known-hosts"])
def test_saves_replace_the_file_atomically(tmp_path, monkeypatch, module, save):
    written = []
    real = module.atomic_write_text

    def recording(path, text):
        written.append(Path(path).name)
        real(path, text)

    monkeypatch.setattr(module, "atomic_write_text", recording)
    save(tmp_path / "store.json")
    assert written == ["store.json"]


def test_a_json_line_after_a_torn_line_survives(tmp_path):
    log = tmp_path / "events.jsonl"
    log.write_text('{"a": 1}\n{"b": ', encoding="utf-8")   # the last write was cut off
    append_json_line(log, json.dumps({"c": 3}))
    lines = log.read_text(encoding="utf-8").splitlines()
    assert json.loads(lines[-1]) == {"c": 3}


def test_a_failed_first_read_does_not_wipe_the_locator_counts(tmp_path, monkeypatch):
    path = tmp_path / "ab.json"
    first = ABStore(path)
    for _ in range(5):
        first.record(target_id="t", strategy="s", succeeded=True, elapsed_ms=1.0)

    store = ABStore(path)
    real_read = Path.read_text
    failures = iter([PermissionError("locked by antivirus")])

    def flaky_read(self, *args, **kwargs):
        error = next(failures, None)
        if error is not None:
            raise error
        return real_read(self, *args, **kwargs)

    monkeypatch.setattr(Path, "read_text", flaky_read)
    with pytest.raises(PermissionError):
        store.record(target_id="t", strategy="s", succeeded=True, elapsed_ms=1.0)
    stats = store.record(target_id="t", strategy="s", succeeded=True, elapsed_ms=1.0)
    assert stats.successes == 6
