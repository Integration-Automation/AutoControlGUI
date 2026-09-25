"""Remote-desktop data from files, servers and the operator (no Qt).

The signaling client and the USB browser's fetch went around http_client: file://
URLs were read, a URL with no scheme raised ValueError past the GUI workers, a
redirect received the secret or the bearer token, and a non-object reply raised
AttributeError. The address book kept tags it could not render; the target
parser kept IPv6 brackets and read ``WSS://`` as a host.
"""
import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest

from je_auto_control.utils.remote_desktop import signaling_client
from je_auto_control.utils.remote_desktop.address_book import AddressBook
from je_auto_control.utils.remote_desktop.connect_coordinator import parse_target


class _Recorder(BaseHTTPRequestHandler):
    """Answer every GET from ``server.reply`` and record the headers it got."""

    def do_GET(self):  # noqa: N802 -- http.server's handler name
        self.server.seen.append(dict(self.headers.items()))
        status, headers, body = self.server.reply
        self.send_response(status)
        for name, value in headers.items():
            self.send_header(name, value)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *_args):
        return


@pytest.fixture()
def serve():
    servers = []

    def start(status=200, headers=None, body=b"{}"):
        server = ThreadingHTTPServer(("127.0.0.1", 0), _Recorder)
        server.seen, server.reply = [], (status, headers or {}, body)
        threading.Thread(target=server.serve_forever, daemon=True).start()
        servers.append(server)
        return server, "http://127.0.0.1:%d" % server.server_address[1]  # NOSONAR loopback test server

    yield start
    for server in servers:
        server.shutdown()
        server.server_close()


# --- the signaling client ------------------------------------------------------------------------------

@pytest.mark.parametrize("url", ["file:///etc/hosts", "signal.example/sessions/h/offer"])
def test_a_url_that_is_not_http_is_a_signaling_error(url):
    with pytest.raises(signaling_client.SignalingError):
        signaling_client._request("GET", url, timeout=1)


def test_the_signaling_secret_does_not_follow_a_redirect(serve):
    target, target_url = serve()
    _, redirecting_url = serve(302, {"Location": target_url + "/sessions/h/offer"})
    with pytest.raises(signaling_client.SignalingError, match="302"):
        signaling_client.fetch_offer(redirecting_url, "h", secret="s3cret")
    assert target.seen == []


@pytest.mark.parametrize("body", [b"[1, 2]", b'{"sdp": 5}'])
def test_a_reply_of_the_wrong_shape_is_a_signaling_error(serve, body):
    _, url = serve(body=body)
    with pytest.raises(signaling_client.SignalingError):
        signaling_client.fetch_offer(url, "h")


def test_an_offer_still_round_trips(serve):
    server, url = serve(body=json.dumps({"sdp": "v=0"}).encode())
    assert signaling_client.fetch_offer(url, "h", secret="s3cret") == "v=0"
    assert server.seen[0]["X-Signaling-Secret"] == "s3cret"


# --- the USB browser's fetch -------------------------------------------------------------------------------

def test_the_bearer_token_does_not_follow_a_redirect_to_another_host(serve):
    pytest.importorskip("PySide6.QtWidgets", exc_type=ImportError)
    from je_auto_control.gui.usb_browser_tab import fetch_remote_devices
    target, target_url = serve(body=b'{"devices": []}')
    _, redirecting_url = serve(302, {"Location": target_url + "/usb/devices"})
    assert fetch_remote_devices(base_url=redirecting_url, token="tok-123") == []
    assert target.seen and "Authorization" not in target.seen[0]


# --- the address book and the target parser -----------------------------------------------------------------

def test_address_book_tags_and_times_are_normalised_on_load(tmp_path):
    path = tmp_path / "book.json"
    path.write_text(json.dumps({"entries": [
        {"host_id": "a", "server_url": "u", "tags": "work", "last_used": 5},
        {"host_id": "b", "server_url": "u", "tags": [1, " home ", ""]},
    ]}), encoding="utf-8")
    first, second = AddressBook(path).list_entries()
    assert first["tags"] == [] and "last_used" not in first
    assert second["tags"] == ["home"]


def test_a_bracketed_ipv6_host_loses_its_brackets():
    target = parse_target("[::1]:5555")
    assert (target.kind, target.host, target.port) == ("tcp", "::1", 5555)


def test_schemes_are_case_insensitive():
    target = parse_target("WSS://desk.example:8443/rd")
    assert (target.kind, target.host, target.port, target.path) == ("wss", "desk.example", 8443, "/rd")
