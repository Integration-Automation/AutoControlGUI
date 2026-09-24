"""A read error is not damage: stores must not move a good file aside (2026-09-24).

``load_json_or_quarantine`` quarantined on any ``OSError``, so one transient
PermissionError (an antivirus scan holding the file) moved a healthy
known_hosts / trust list / address book aside and the store started empty.
"""
import json
from pathlib import Path

import pytest

from je_auto_control.utils.admin.admin_client import AdminConsoleClient
from je_auto_control.utils.json_store.json_store import load_json_or_quarantine


def _locked(monkeypatch, target):
    original = Path.read_text

    def read_text(self, *args, **kwargs):
        if Path(self) == Path(target):
            raise PermissionError("locked by a scan")
        return original(self, *args, **kwargs)

    monkeypatch.setattr(Path, "read_text", read_text)


def test_a_locked_file_propagates_and_stays_in_place(tmp_path, monkeypatch):
    path = tmp_path / "known_hosts.json"
    path.write_text(json.dumps({"h": {"fingerprint": "ab"}}), encoding="utf-8")
    _locked(monkeypatch, path)
    with pytest.raises(PermissionError):
        load_json_or_quarantine(path, "known_hosts")
    assert path.exists() and not list(tmp_path.glob("*.corrupt-*"))


def test_damaged_content_is_still_quarantined(tmp_path):
    path = tmp_path / "store.json"
    path.write_text("{not json", encoding="utf-8")
    assert load_json_or_quarantine(path, "store") is None
    assert list(tmp_path.glob("store.json.corrupt-*"))
    raw = tmp_path / "raw.json"
    raw.write_bytes(b"\xff\xfe\x00bad")
    assert load_json_or_quarantine(raw, "store") is None
    assert list(tmp_path.glob("raw.json.corrupt-*"))


def test_a_missing_file_is_none(tmp_path):
    assert load_json_or_quarantine(tmp_path / "absent.json", "store") is None


def test_the_admin_host_list_is_not_emptied_by_a_locked_file(tmp_path, monkeypatch):
    path = tmp_path / "hosts.json"
    path.write_text(json.dumps({"hosts": []}), encoding="utf-8")
    _locked(monkeypatch, path)
    with pytest.raises(PermissionError):
        AdminConsoleClient(persist_path=path)
    assert not list(tmp_path.glob("*.corrupt-*"))
