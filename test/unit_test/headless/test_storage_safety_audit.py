"""Stores keep their data and their secrets under contention and odd input.

Two secret managers writing one vault lost secrets and raised
``PermissionError``; a UTF-8 BOM made a shared JSON store read as empty and the
next update wrote back one key; a reader holding the file open failed a write
on Windows; cassettes kept ``set_cookie`` in clear; a truncated deflate body
came back as if whole, and ``x-gzip`` was refused; SQLite stores let
``sqlite3.Error`` escape the ``AutoControlException`` family.
"""
import threading
import zlib

import pytest

from je_auto_control.utils.checkpoint.checkpoint import CheckpointStore, CheckpointStoreError
from je_auto_control.utils.exception.exceptions import AutoControlException
from je_auto_control.utils.http_cassette.http_cassette import REDACTED, Cassette
from je_auto_control.utils.http_content.http_content import decode_body
from je_auto_control.utils.json_store.json_store import SharedJsonDict, write_json_dict
from je_auto_control.utils.work_queue.work_queue import WorkQueue, WorkQueueError


def test_two_vault_managers_keep_every_secret(tmp_path, monkeypatch):
    pytest.importorskip("cryptography")
    from je_auto_control.utils.secrets import secret_store
    monkeypatch.setattr(secret_store, "_KEY_ITERATIONS", 1_000)
    path = tmp_path / "vault.json"
    first = secret_store.SecretManager(path)
    first.initialize("pw")
    second = secret_store.SecretManager(path)
    assert second.unlock("pw")
    errors = []

    def writer(manager, prefix):
        for index in range(25):
            try:
                manager.set(f"{prefix}{index}", "v")
            except Exception as error:  # noqa: BLE001  # reason: the test collects every failure to report it
                errors.append(repr(error))

    threads = [threading.Thread(target=writer, args=(first, "a")),
               threading.Thread(target=writer, args=(second, "b"))]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    assert errors == []
    assert len(first.list_names()) == 50


def test_a_bom_does_not_empty_a_shared_store(tmp_path):
    path = tmp_path / "store.json"
    path.write_bytes(b"\xef\xbb\xbf" + b'{"keep": 1, "also": 2}')
    SharedJsonDict(path).update(lambda data: data.__setitem__("new", 3))
    assert SharedJsonDict(path).read() == {"keep": 1, "also": 2, "new": 3}


def test_a_write_waits_for_a_reader_to_let_go(tmp_path):
    path = tmp_path / "store.json"
    write_json_dict(path, {"a": 1})
    handle = open(path, encoding="utf-8")  # noqa: SIM115  # reason: held open across the write on purpose
    closer = threading.Timer(0.2, handle.close)
    closer.start()
    try:
        write_json_dict(path, {"a": 2})
    finally:
        closer.join()
        handle.close()
    assert SharedJsonDict(path).read() == {"a": 2}


def test_a_cassette_redacts_the_set_cookie_list():
    cassette = Cassette()
    cassette.record({"method": "GET", "url": "https://x/"},
                    {"status": 200, "headers": {"Set-Cookie": "sid=SECRET"},
                     "set_cookie": ["sid=SECRET", "other=SECRET2"]})
    response = cassette.interactions[0]["response"]
    assert response["set_cookie"] == [REDACTED, REDACTED]
    assert "SECRET" not in repr(response)


def test_a_truncated_deflate_body_is_refused_and_x_gzip_is_gzip():
    body = zlib.compress(b"A" * 1000)
    assert decode_body({"Content-Encoding": "deflate"}, body) == b"A" * 1000
    raw_stream = zlib.compressobj(wbits=-zlib.MAX_WBITS)
    raw_body = raw_stream.compress(b"B" * 50) + raw_stream.flush()
    assert decode_body({"Content-Encoding": "deflate"}, raw_body) == b"B" * 50
    with pytest.raises(ValueError, match="truncated"):
        decode_body({"Content-Encoding": "deflate"}, body[:-12])
    import gzip
    assert decode_body({"Content-Encoding": "x-gzip"}, gzip.compress(b"hi")) == b"hi"


@pytest.mark.parametrize("store, error", [(WorkQueue, WorkQueueError),
                                          (CheckpointStore, CheckpointStoreError)])
def test_a_store_on_a_non_database_raises_its_own_error(tmp_path, store, error):
    path = tmp_path / "not.db"
    path.write_bytes(b"this is not a database" * 100)
    with pytest.raises(error) as caught:
        store(str(path))
    assert isinstance(caught.value, AutoControlException)
