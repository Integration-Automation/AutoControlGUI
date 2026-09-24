"""Admin console defects from the 2026-09-24 audit (local servers, fake token).

A host that redirected got the bearer token re-sent to the redirect target;
``timeout_s`` bounded each read, not the request, and bodies were unbounded;
a broadcast to an unknown label dropped it silently; a whitespace-only label
was accepted; and malformed or damaged host files lost entries on save.
"""
import json
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest

from je_auto_control.utils.admin.admin_client import AdminConsoleClient

TOKEN = "test-token-1"


def _serve(handler):
    server = ThreadingHTTPServer(("127.0.0.1", 0), handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return server


@pytest.fixture
def console(tmp_path):
    return AdminConsoleClient(persist_path=tmp_path / "admin_hosts.json", timeout_s=1.0)


def test_a_redirect_does_not_carry_the_token(console):
    seen = []

    class Target(BaseHTTPRequestHandler):
        def do_GET(self):  # noqa: N802
            seen.append(self.headers.get("Authorization"))
            self.send_response(200)
            self.end_headers()
            self.wfile.write(b"{}")

        def log_message(self, *_args):
            pass

    target = _serve(Target)

    class Redirector(BaseHTTPRequestHandler):
        def do_GET(self):  # noqa: N802
            self.send_response(302)
            self.send_header("Location", f"http://127.0.0.1:{target.server_address[1]}/sessions")
            self.end_headers()

        def log_message(self, *_args):
            pass

    source = _serve(Redirector)
    try:
        console.add_host("h", f"http://127.0.0.1:{source.server_address[1]}", TOKEN)
        status = console.poll_all()[0]
        assert status.healthy is False
        assert seen == []
    finally:
        source.shutdown()
        target.shutdown()


def test_a_dripping_host_is_cut_off_at_the_timeout(console):
    class Drip(BaseHTTPRequestHandler):
        def do_GET(self):  # noqa: N802
            self.send_response(200)
            self.end_headers()
            try:
                for _ in range(40):
                    self.wfile.write(b" ")
                    self.wfile.flush()
                    time.sleep(0.2)
            except OSError:
                pass

        def log_message(self, *_args):
            pass

    server = _serve(Drip)
    try:
        console.add_host("h", f"http://127.0.0.1:{server.server_address[1]}", TOKEN)
        started = time.monotonic()
        assert console.poll_all()[0].healthy is False
        assert time.monotonic() - started < 3.0
    finally:
        server.shutdown()


def test_an_unknown_label_is_reported(console):
    rows = console.broadcast_execute([["AC_screen_size"]], labels=["typo-host"])
    assert rows == [{"label": "typo-host", "ok": False, "error": "unknown host"}]


def test_a_whitespace_label_is_refused(console):
    with pytest.raises(ValueError):
        console.add_host("   ", "http://127.0.0.1:1", TOKEN)


def test_a_malformed_entry_survives_the_next_save(tmp_path):
    path = tmp_path / "admin_hosts.json"
    path.write_text(json.dumps({"hosts": [
        {"label": "a", "base_url": "http://a", "token": TOKEN},
        {"label": "b", "base_url": "http://b", "token": TOKEN, "future_field": 1},
    ]}), encoding="utf-8")
    AdminConsoleClient(persist_path=path).add_host("c", "http://c", TOKEN)
    labels = [entry["label"] for entry in json.loads(path.read_text(encoding="utf-8"))["hosts"]]
    assert sorted(labels) == ["a", "b", "c"]


def test_a_damaged_file_is_kept_aside(tmp_path):
    path = tmp_path / "admin_hosts.json"
    path.write_text('{"hosts": [{"label": "a", "base_url": "http://a", "tok', encoding="utf-8")
    AdminConsoleClient(persist_path=path).add_host("z", "http://z", TOKEN)
    assert len([p for p in tmp_path.iterdir() if p.name.startswith("admin_hosts.json.corrupt-")]) == 1


def test_the_usb_viewer_caps_a_message_without_eof():
    from je_auto_control.utils.usb.passthrough import viewer_client
    from je_auto_control.utils.usb.passthrough.protocol import Frame, Opcode
    client = viewer_client.UsbPassthroughClient(send_frame=lambda _frame: None)
    chunk = b"x" * 16384
    for _ in range(200):
        client._reassemble(Frame(op=Opcode.BULK, claim_id=99, payload=chunk))
    assert sum(len(buffer) for buffer in client._reasm.values()) <= viewer_client._MAX_REASSEMBLED_BYTES
