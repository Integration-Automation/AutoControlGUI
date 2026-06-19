"""Headless tests for the S3 artifact store. A fake S3 client implements the
four boto3 methods used, so the store's logic (and the executor path) is fully
tested without boto3 or network. Pure stdlib, no Qt imports."""
from pathlib import Path

import pytest

import je_auto_control as ac
from je_auto_control.utils.artifact_store import (
    S3ArtifactStore, configure_default_store, get_default_store,
    set_default_store)


class _FakeS3:
    """Minimal stand-in for a boto3 S3 client (in-memory object store)."""

    def __init__(self):
        self.objects = {}

    def upload_file(self, filename, bucket, key):
        self.objects[(bucket, key)] = Path(filename).read_bytes()

    def download_file(self, bucket, key, filename):
        Path(filename).write_bytes(self.objects[(bucket, key)])

    def list_objects_v2(self, Bucket, Prefix=""):
        keys = [k for (b, k) in self.objects if b == Bucket
                and k.startswith(Prefix)]
        return {"Contents": [{"Key": k} for k in sorted(keys)]}

    def delete_object(self, Bucket, Key):
        self.objects.pop((Bucket, Key), None)


@pytest.fixture
def store():
    return S3ArtifactStore("my-bucket", client=_FakeS3(), prefix="runs/42")


def test_upload_returns_relative_key_and_prefixed_url(tmp_path, store):
    art = tmp_path / "report.html"
    art.write_text("<html></html>", encoding="utf-8")
    key = store.upload(str(art))
    assert key == "report.html"          # store-relative
    assert store.url(key) == "s3://my-bucket/runs/42/report.html"


def test_upload_explicit_key(tmp_path, store):
    art = tmp_path / "a.txt"
    art.write_text("x", encoding="utf-8")
    assert store.upload(str(art), key="nested/out.txt") == "nested/out.txt"


def test_round_trip_download(tmp_path, store):
    art = tmp_path / "data.bin"
    art.write_bytes(b"\x00\x01\x02")
    store.upload(str(art), key="data.bin")
    dest = tmp_path / "out" / "data.bin"
    store.download("data.bin", str(dest))
    assert dest.read_bytes() == b"\x00\x01\x02"


def test_list_and_delete(tmp_path, store):
    for name in ("a.txt", "b.txt"):
        p = tmp_path / name
        p.write_text(name, encoding="utf-8")
        store.upload(str(p))
    assert sorted(store.list()) == ["a.txt", "b.txt"]
    assert store.delete("a.txt") is True
    assert store.list() == ["b.txt"]


def test_get_default_store_unconfigured_raises():
    set_default_store(None)
    with pytest.raises(RuntimeError):
        get_default_store()


# --- wiring ---------------------------------------------------------------

def test_executor_round_trip_with_fake_client(tmp_path):
    configure_default_store("bkt", client=_FakeS3(), prefix="ci")
    try:
        art = tmp_path / "log.txt"
        art.write_text("hello", encoding="utf-8")
        rec = ac.execute_action([
            ["AC_s3_upload", {"local_path": str(art), "key": "log.txt"}],
        ])
        assert next(v for v in rec.values()
                    if isinstance(v, dict))["key"] == "log.txt"
        rec2 = ac.execute_action([["AC_s3_list", {}]])
        assert "log.txt" in next(v for v in rec2.values()
                                 if isinstance(v, dict))["keys"]
    finally:
        set_default_store(None)          # leave global state clean


def test_wiring():
    known = ac.executor.known_commands()
    assert {"AC_s3_upload", "AC_s3_download", "AC_s3_list",
            "AC_s3_delete"} <= known
    from je_auto_control.utils.mcp_server.tools import (
        build_default_tool_registry)
    names = {t.name for t in build_default_tool_registry()}
    assert {"ac_s3_upload", "ac_s3_download", "ac_s3_list",
            "ac_s3_delete"} <= names
    from je_auto_control.gui.script_builder.command_schema import _build_specs
    cmds = {s.command for s in _build_specs()}
    assert {"AC_s3_upload", "AC_s3_download", "AC_s3_list",
            "AC_s3_delete"} <= cmds


def test_facade_exports():
    for attr in ("S3ArtifactStore", "configure_default_store",
                 "get_default_store", "set_default_store"):
        assert hasattr(ac, attr)
        assert attr in ac.__all__
