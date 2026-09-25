"""Integration helpers at the edges the audit found (loopback servers and fakes only).

Secrets nested in an argument were logged; a truncated error body escaped
http_client; assert_http and config sync bypassed the egress policy and the
redirect checks; Office, S3 and SQLite errors escaped the framework family;
the IMAP trigger double-fired, ignored UIDVALIDITY and could not name a
non-ASCII mailbox; X-Api-Key followed a redirect; cassettes kept credentials
outside headers; a deeply nested reply crashed http_request.
"""
import json
import socket
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest

from je_auto_control.utils.exception.exceptions import AutoControlActionException, AutoControlException
from je_auto_control.utils.executor.action_redaction import describe_action

_SECRET = "FAKE-" + "SECRET-123"


# --- redaction -------------------------------------------------------------------------------------

@pytest.mark.parametrize("action", [
    ["AC_send_email", {"to": "a@b.c", "smtp": {"host": "h", "password": _SECRET}}],
    ["AC_http_to_var", {"url": "https://x", "headers": {"Authorization": f"Bearer {_SECRET}",
                                                        "X-Api-Key": _SECRET}}],
    ["AC_notify_webhook", {"url": f"https://hooks.slack.com/services/{_SECRET}", "text": "hi"}],
])
def test_nested_secrets_and_webhook_urls_are_masked(action):
    assert _SECRET not in describe_action(action)


# --- loopback servers ---------------------------------------------------------------------------------

class _Recorder(BaseHTTPRequestHandler):
    seen = []
    redirect_to = None

    def _answer(self):
        type(self).seen.append((self.path, dict(self.headers)))
        if type(self).redirect_to and self.path == "/start":
            self.send_response(302)
            self.send_header("Location", type(self).redirect_to + "/landed")
            self.send_header("Content-Length", "0")
            self.end_headers()
            return
        body = b'{"ok": true}'
        self.send_response(200)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    do_GET = do_PUT = do_POST = _answer

    def log_message(self, format, *args):  # noqa: A002  # pylint: disable=redefined-builtin  # reason: stdlib override
        return


def _serve(handler):
    server = ThreadingHTTPServer(("127.0.0.1", 0), handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return server, "http://127.0.0.1:%d" % server.server_address[1]  # NOSONAR loopback test server


@pytest.fixture()
def two_origins():
    first_handler = type("First", (_Recorder,), {"seen": []})
    second_handler = type("Second", (_Recorder,), {"seen": []})
    first, first_url = _serve(first_handler)
    second, second_url = _serve(second_handler)
    # "localhost" and "127.0.0.1" are two origins on the same machine.
    first_handler.redirect_to = second_url.replace("127.0.0.1", "localhost")
    yield first_url, first_handler, second_handler
    for server in (first, second):
        server.shutdown()
        server.server_close()


def test_an_api_key_does_not_follow_a_redirect_to_another_origin(two_origins):
    from je_auto_control.utils.http_client.http_client import http_request
    first_url, _first, second = two_origins
    http_request(first_url + "/start", headers={"X-Api-Key": _SECRET, "Authorization": _SECRET})
    assert second.seen and all(_SECRET not in repr(headers) for _path, headers in second.seen)


def test_config_sync_does_not_carry_its_secret_through_a_redirect(two_origins):
    from je_auto_control.utils.config_sync.client import ConfigSyncClient, ConfigSyncError
    first_url, first, _second = two_origins
    # The sync server answers 302 to another origin (the first server, as
    # "localhost"): not followed, so the secret never reaches it.
    with pytest.raises(ConfigSyncError, match="302"):
        _fetch_through_redirect(first_url, ConfigSyncClient)
    assert first.seen == []


def _fetch_through_redirect(first_url, client_cls):
    class _Redirect(BaseHTTPRequestHandler):
        def do_GET(self):  # noqa: N802  # reason: stdlib API
            self.send_response(302)
            self.send_header("Location", first_url.replace("127.0.0.1", "localhost") + "/elsewhere")
            self.send_header("Content-Length", "0")
            self.end_headers()

        def log_message(self, format, *args):  # noqa: A002  # pylint: disable=redefined-builtin  # reason: stdlib override
            return

    redirecting, redirect_url = _serve(_Redirect)
    try:
        return client_cls(redirect_url, user_id="u", secret=_SECRET).fetch()
    finally:
        redirecting.shutdown()
        redirecting.server_close()


@pytest.fixture()
def locked_egress():
    from je_auto_control.utils.egress.egress_policy import set_egress_policy
    set_egress_policy(allow=["api.example.com"])
    yield
    set_egress_policy()


def test_assert_http_obeys_the_egress_policy(two_origins, locked_egress):
    from je_auto_control.utils.assertion.assertions import assert_http
    from je_auto_control.utils.egress.egress_policy import EgressBlocked
    first_url, first, _second = two_origins
    with pytest.raises(EgressBlocked):
        assert_http(first_url + "/internal", raise_on_fail=False)
    assert first.seen == []


def test_a_truncated_error_body_is_an_oserror():
    from je_auto_control.utils.http_client.http_client import http_request
    listener = socket.socket()
    listener.bind(("127.0.0.1", 0))
    listener.listen(1)

    def serve():
        conn, _ = listener.accept()
        conn.recv(65536)
        conn.sendall(b"HTTP/1.1 500 Oops\r\nTransfer-Encoding: chunked\r\n\r\n10\r\nabc")
        conn.close()

    threading.Thread(target=serve, daemon=True).start()
    try:
        with pytest.raises(OSError):
            http_request("http://127.0.0.1:%d/t500" % listener.getsockname()[1])  # NOSONAR loopback test server
    finally:
        listener.close()


def test_a_reply_nested_too_deeply_is_not_json(monkeypatch):
    from je_auto_control.utils.http_client import http_client

    def too_deep(_text):
        raise RecursionError("maximum recursion depth exceeded while decoding a JSON array")

    monkeypatch.setattr(http_client.json, "loads", too_deep)
    assert http_client._try_json("[[[]]]") is None  # noqa: SLF001


# --- Office, S3, SQLite ------------------------------------------------------------------------------

def test_a_file_that_is_not_a_workbook_is_an_action_error(tmp_path):
    pytest.importorskip("openpyxl")
    from je_auto_control.utils.office.office import read_workbook
    fake = tmp_path / "data.xlsx"
    fake.write_text("a,b\n1,2\n", encoding="utf-8")
    with pytest.raises(AutoControlActionException, match="workbook"):
        read_workbook(str(fake))


def test_s3_client_errors_are_in_the_framework_family():
    from je_auto_control.utils.artifact_store.s3_store import ArtifactStoreError, S3ArtifactStore

    class ClientError(Exception):
        pass

    class _Client:
        def delete_object(self, **_kwargs):
            raise ClientError("AccessDenied")

        def list_objects_v2(self, **_kwargs):
            raise ClientError("AccessDenied")

    store = S3ArtifactStore("bucket", client=_Client())
    for call in (lambda: store.delete("k"), store.list):
        with pytest.raises(ArtifactStoreError, match="AccessDenied"):
            call()
    assert issubclass(ArtifactStoreError, AutoControlException)


def test_a_sqlite_file_that_cannot_be_opened_is_an_action_error(tmp_path, monkeypatch):
    import sqlite3

    from je_auto_control.utils.data_source import data_source

    class _Locked:
        Row = sqlite3.Row

        @staticmethod
        def connect(*_args, **_kwargs):
            raise sqlite3.OperationalError("unable to open database file")

    monkeypatch.setattr(data_source, "require_sqlite3", lambda: _Locked)
    database = tmp_path / "held.db"
    database.write_bytes(b"")
    with pytest.raises(AutoControlActionException, match="SQLite"):
        data_source.load_rows({"kind": "sqlite", "path": str(database), "query": "SELECT 1"})


# --- IMAP trigger -------------------------------------------------------------------------------------

def _trigger():
    from je_auto_control.utils.triggers.email_trigger import EmailTrigger
    return EmailTrigger(trigger_id="t", host="h", username="u", password="p", script_path="s.json")


def test_a_message_is_claimed_by_one_poll_only():
    from je_auto_control.utils.triggers.email_trigger import EmailTriggerWatcher
    watcher, trigger = EmailTriggerWatcher(), _trigger()
    assert watcher._claim(trigger, "1") is True  # noqa: SLF001
    assert watcher._claim(trigger, "1") is False  # noqa: SLF001


def test_a_new_uidvalidity_forgets_the_seen_uids():
    from je_auto_control.utils.triggers.email_trigger import EmailTriggerWatcher
    watcher, trigger = EmailTriggerWatcher(), _trigger()

    class _Client:
        def __init__(self, value):
            self.value = value

        def response(self, code):
            return code, [self.value]

    watcher._check_uidvalidity(_Client(b"7"), trigger)  # noqa: SLF001
    trigger._seen_uids.add("1")  # noqa: SLF001
    watcher._check_uidvalidity(_Client(b"7"), trigger)  # noqa: SLF001
    assert trigger._seen_uids == {"1"}  # noqa: SLF001
    watcher._check_uidvalidity(_Client(b"8"), trigger)  # noqa: SLF001
    assert trigger._seen_uids == set()  # noqa: SLF001


@pytest.mark.parametrize("name, wire", [
    ("台北", '"&U,BTFw-"'),
    ("日本語", '"&ZeVnLIqe-"'),
    ("R&D", '"R&-D"'),
    ("&ZeVnLIqe-", '"&ZeVnLIqe-"'),
    ("Sent Items", '"Sent Items"'),
])
def test_mailbox_names_go_out_in_modified_utf7(name, wire):
    from je_auto_control.utils.triggers.email_trigger import _quote_mailbox
    assert _quote_mailbox(name) == wire


# --- cassettes ----------------------------------------------------------------------------------------

def test_a_cassette_keeps_no_credential_and_still_replays(tmp_path):
    from je_auto_control.utils.http_cassette.http_cassette import Cassette
    call = {"method": "POST", "url": f"https://api.example.com/x?api_key={_SECRET}&q=1",
            "headers": {}, "body": json.dumps({"user": "u", "password": _SECRET})}
    response = {"status": 200, "text": json.dumps({"access_token": _SECRET}),
                "json": {"access_token": _SECRET}}
    cassette = Cassette()
    cassette.record(call, response)
    path = cassette.save(str(tmp_path / "c.json"))
    assert _SECRET not in open(path, encoding="utf-8").read()
    replayed = Cassette.load(path).replay(call, match_on=("method", "url", "body"))
    assert replayed["status"] == 200
