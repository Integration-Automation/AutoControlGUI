"""Regression tests for the file-transfer / admin defects of the 2026-09-23 audit.

The plain-socket receiver truncated the destination before any data arrived,
kept writing past the announced size, reported short transfers as success,
leaked a handle on a repeated transfer id, and let a bad destination kill the
receive thread. The WebRTC inbox had the same size gaps, accepted Windows
device names and malformed envelopes, and one misbehaving admin host failed
every host's poll.
"""
import http.client
import json
import os
import socket
import threading

import pytest

from je_auto_control.utils.admin.admin_client import AdminConsoleClient
from je_auto_control.utils.exception.exceptions import AutoControlException
from je_auto_control.utils.package_manager.package_manager_class import PackageManager
from je_auto_control.utils.remote_desktop import file_transfer as ft
from je_auto_control.utils.remote_desktop import webrtc_files as wf


# --- plain-socket receiver ----------------------------------------------------

def _receiver():
    done = []
    receiver = ft.FileReceiver(on_complete=lambda tid, ok, err, dst: done.append((ok, err)))
    return receiver, done


def _transfer(receiver, dest, chunks, size, status="ok"):
    tid = ft.new_transfer_id()
    receiver.handle_begin(ft.encode_begin(tid, str(dest), size))
    for chunk in chunks:
        receiver.handle_chunk(ft.encode_chunk(tid, chunk))
    receiver.handle_end(ft.encode_end(tid, status))
    return tid


def test_a_complete_transfer_lands_with_no_part_file(tmp_path):
    receiver, done = _receiver()
    _transfer(receiver, tmp_path / "f.bin", [b"ab", b"cd"], 4)
    assert done == [(True, None)]
    assert (tmp_path / "f.bin").read_bytes() == b"abcd"
    assert os.listdir(tmp_path) == ["f.bin"]


def test_a_failed_transfer_keeps_the_existing_file(tmp_path):
    target = tmp_path / "keep.txt"
    target.write_bytes(b"IMPORTANT")
    receiver, done = _receiver()
    _transfer(receiver, target, [b"half"], 8, status="error")
    assert done[0][0] is False
    assert target.read_bytes() == b"IMPORTANT"
    assert os.listdir(tmp_path) == ["keep.txt"]


def test_more_data_than_announced_fails(tmp_path):
    receiver, done = _receiver()
    _transfer(receiver, tmp_path / "f.bin", [b"x" * 10], 1)
    assert done[0][0] is False and "announced" in done[0][1]
    assert not (tmp_path / "f.bin").exists()


def test_a_short_transfer_is_not_a_success(tmp_path):
    receiver, done = _receiver()
    _transfer(receiver, tmp_path / "f.bin", [b"abc"], 1000)
    assert done[0][0] is False and "3 of 1000" in done[0][1]
    assert os.listdir(tmp_path) == []


def test_a_bad_destination_fails_the_transfer_instead_of_raising(tmp_path):
    receiver, done = _receiver()
    tid = ft.new_transfer_id()
    receiver.handle_begin(ft.encode_begin(tid, str(tmp_path / "a\x00b"), 1))
    assert done and done[0][0] is False


def test_a_repeated_transfer_id_does_not_replace_the_first(tmp_path):
    receiver, done = _receiver()
    tid = ft.new_transfer_id()
    receiver.handle_begin(ft.encode_begin(tid, str(tmp_path / "one"), 2))
    receiver.handle_begin(ft.encode_begin(tid, str(tmp_path / "two"), 2))
    receiver.handle_chunk(ft.encode_chunk(tid, b"hi"))
    receiver.handle_end(ft.encode_end(tid))
    assert done == [(True, None)]
    assert (tmp_path / "one").read_bytes() == b"hi"
    assert not (tmp_path / "two").exists()


# --- WebRTC inbox -------------------------------------------------------------

def _inbox(tmp_path):
    receiver = wf.FileTransferReceiver(inbox_dir=tmp_path)
    events = {"done": [], "errors": []}

    def send(message):
        receiver.handle_message(message, on_done=events["done"].append,
                                on_error=events["errors"].append)
    return send, events


def _begin(name, size):
    return json.dumps({"type": "file_begin", "name": name, "size": size, "transfer_id": "t"})


_END = json.dumps({"type": "file_end", "transfer_id": "t"})


@pytest.mark.parametrize("name", ["nul", "CON", "aux.log", "COM1.txt", "report. ", "a ", "tab\tname"])
def test_names_windows_would_redirect_are_refused(tmp_path, name):
    send, events = _inbox(tmp_path)
    send(_begin(name, 1))
    assert events["errors"] and not events["done"]


def test_the_inbox_rejects_more_data_than_announced(tmp_path):
    send, events = _inbox(tmp_path)
    send(_begin("big.bin", 10))
    send(b"x" * 5000)
    assert events["errors"]
    assert os.listdir(tmp_path) == []


def test_the_inbox_rejects_a_truncated_file_and_keeps_the_old_copy(tmp_path):
    (tmp_path / "keep.txt").write_bytes(b"IMPORTANT")
    send, events = _inbox(tmp_path)
    send(_begin("keep.txt", 1000))
    send(b"abc")
    send(_END)
    assert events["errors"] and not events["done"]
    assert (tmp_path / "keep.txt").read_bytes() == b"IMPORTANT"
    assert os.listdir(tmp_path) == ["keep.txt"]


def test_the_inbox_replaces_a_file_only_when_complete(tmp_path):
    (tmp_path / "keep.txt").write_bytes(b"old")
    send, events = _inbox(tmp_path)
    send(_begin("keep.txt", 3))
    send(b"new")
    send(_END)
    assert events["done"] and (tmp_path / "keep.txt").read_bytes() == b"new"
    assert os.listdir(tmp_path) == ["keep.txt"]


@pytest.mark.parametrize("envelope", ["[1, 2]", _begin("a", "abc"), _begin("a", None),
                                      '{"type": "file_begin", "name": "a", "size": 1e400}'])
def test_a_malformed_envelope_is_a_protocol_error(tmp_path, envelope):
    send, events = _inbox(tmp_path)
    send(envelope)
    assert events["errors"]


def test_transfer_errors_are_in_the_framework_family():
    assert issubclass(ft.FileTransferError, AutoControlException)
    assert issubclass(wf.FileTransferError, AutoControlException)


# --- admin client / package manager -------------------------------------------

def _garbage_host():
    listener = socket.socket()
    listener.bind(("127.0.0.1", 0))
    listener.listen(4)

    def serve():
        for _ in range(3):
            try:
                connection, _ = listener.accept()
            except OSError:
                return
            with connection:
                connection.recv(4096)
                connection.sendall(b"GARBAGE\r\n\r\n")
        listener.close()

    threading.Thread(target=serve, daemon=True).start()
    return listener.getsockname()[1]


def test_one_malformed_admin_host_does_not_fail_the_poll(tmp_path):
    client = AdminConsoleClient(persist_path=tmp_path / "hosts.json")
    client.add_host("bad", f"http://127.0.0.1:{_garbage_host()}", "t")
    statuses = client.poll_all()
    assert [status.healthy for status in statuses] == [False]
    assert issubclass(http.client.BadStatusLine, http.client.HTTPException)


def test_an_address_book_whose_hosts_is_not_a_list_loads_empty(tmp_path):
    book = tmp_path / "hosts.json"
    book.write_text('{"hosts": 5}', encoding="utf-8")
    assert AdminConsoleClient(persist_path=book).list_hosts() == []


def test_a_missing_parent_package_is_reported_not_raised():
    assert PackageManager().check_package("no_such_parent_pkg_x.child") is None
