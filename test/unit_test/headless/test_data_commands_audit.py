"""Regression tests for the data-command defects of the 2026-09-23 audit.

Seven error types from the data commands (sqlite3, csv, re, pypdf, a TOTP
division by zero, a malformed HTTP reply) were outside every type the
executor contains, so one bad step aborted the whole script under
``raise_on_error=False``. A redirect bypassed the egress policy, and on Windows
a string command reached the child with its quotes doubled.
"""
import http.server
import os
import socket
import sqlite3
import sys
import threading
import urllib.error

import pytest

from je_auto_control.utils.egress.egress_policy import EgressBlocked, set_egress_policy
from je_auto_control.utils.executor.action_executor import Executor
from je_auto_control.utils.http_client import http_client


def _run_then_sentinel(action):
    """Run ``action`` then a sentinel; return (record, whether the sentinel ran)."""
    executor = Executor()
    record = executor.execute_action([action, ["AC_set_var", {"name": "after", "value": 1}]])
    return record, executor.variables.get("after") == 1


@pytest.fixture
def database(tmp_path):
    path = tmp_path / "db.sqlite"
    with sqlite3.connect(path) as connection:
        connection.execute("CREATE TABLE t (a)")
    return str(path)


@pytest.mark.parametrize("action", [
    lambda db, tmp: ["AC_sql_to_var", {"database": db, "query": "SELECT * FROM nope"}],
    lambda db, tmp: ["AC_for_each_row", {"source": {"kind": "sqlite", "path": db,
                                                    "query": "SELECT * FROM nope"}, "body": []}],
    lambda db, tmp: ["AC_transform_var", {"name": "x", "value": "abc", "op": "regex", "pattern": "("}],
    lambda db, tmp: ["AC_otp_to_var", {"secret": "JBSWY3DPEHPK3PXP", "step": 0}],
], ids=["sql", "sqlite-source", "regex", "otp-step"])
def test_a_failing_data_step_is_recorded_and_the_script_goes_on(database, tmp_path, action):
    record, sentinel_ran = _run_then_sentinel(action(database, tmp_path))
    assert sentinel_ran, record


def test_a_csv_field_over_the_limit_is_contained(tmp_path):
    source = tmp_path / "big.csv"
    source.write_text("a\n" + "x" * 200_000 + "\n", encoding="utf-8")
    _, sentinel_ran = _run_then_sentinel(
        ["AC_for_each_row", {"source": {"kind": "csv", "path": str(source)}, "body": []}])
    assert sentinel_ran


def test_a_file_that_is_not_a_pdf_is_contained(tmp_path):
    pytest.importorskip("pypdf")
    fake = tmp_path / "fake.pdf"
    fake.write_bytes(b"%PDF-1.4\nnot really")
    _, sentinel_ran = _run_then_sentinel(["AC_pdf_to_var", {"path": str(fake)}])
    assert sentinel_ran


# --- HTTP ---------------------------------------------------------------------

def _garbage_server():
    listener = socket.socket()
    listener.bind(("127.0.0.1", 0))
    listener.listen(1)

    def answer():
        connection, _ = listener.accept()
        with connection:
            connection.recv(4096)
            connection.sendall(b"GARBAGE\r\n\r\n")
        listener.close()

    threading.Thread(target=answer, daemon=True).start()
    return listener.getsockname()[1]


def test_a_malformed_http_reply_arrives_as_an_oserror():
    port = _garbage_server()
    with pytest.raises(urllib.error.URLError):
        http_client.http_request(f"http://127.0.0.1:{port}/", timeout=5)


class _Redirect(http.server.BaseHTTPRequestHandler):
    def do_GET(self):  # noqa: N802 - http.server naming
        self.send_response(302)
        self.send_header("Location", f"http://localhost:{self.server.server_port}/secret")
        self.end_headers()

    def log_message(self, *_args):
        pass


def test_a_redirect_cannot_leave_the_egress_allow_list():
    server = http.server.HTTPServer(("127.0.0.1", 0), _Redirect)
    threading.Thread(target=server.handle_request, daemon=True).start()
    set_egress_policy(allow=["127.0.0.1"])
    try:
        with pytest.raises(EgressBlocked):
            http_client.http_request(f"http://127.0.0.1:{server.server_port}/", timeout=5)
    finally:
        set_egress_policy()
        server.server_close()


# --- shell --------------------------------------------------------------------

@pytest.mark.skipif(os.name != "nt", reason="the double quoting only happened on Windows")
def test_a_windows_command_string_keeps_its_quoting():
    executor = Executor()
    command = f'"{sys.executable}" -c "import sys; print(sys.argv[1:])" "hello world"'
    executor.execute_action([["AC_shell_to_var", {"command": command}]])
    assert executor.variables.get("shell_output") == "['hello world']"


def test_shell_output_is_decoded_with_the_requested_encoding():
    executor = Executor()
    script = "import sys; sys.stdout.buffer.write('\\u4e2d'.encode('utf-16-le'))"
    executor.execute_action([["AC_shell_to_var", {
        "command": [sys.executable, "-c", script], "encoding": "utf-16-le"}]])
    assert executor.variables.get("shell_output") == "中"
