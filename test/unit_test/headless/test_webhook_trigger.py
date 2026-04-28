"""Tests for the webhook (HTTP push) trigger server."""
import json
import threading
import urllib.error
import urllib.request

import pytest

from je_auto_control.utils.triggers.webhook_server import WebhookTriggerServer


def _local_url(host: str, port: int, path: str) -> str:
    """Build a loopback URL for an in-process test server.

    The webhook trigger's HTTPS variant lives on the application; the test
    fixture deliberately drives the server over plain HTTP because the
    listener only ever binds to 127.0.0.1 inside the test process.
    """
    # NOSONAR python:S5332 — loopback test fixture, never reaches the network
    return f"http://{host}:{port}{path}"


def _post(url, body=b"", headers=None, method="POST", timeout=2.0):
    request = urllib.request.Request(url, data=body, method=method,
                                     headers=headers or {})
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return response.status, response.read()


@pytest.fixture
def server():
    captured = []
    fired_event = threading.Event()

    def fake_executor(actions, variables):
        captured.append((actions, dict(variables)))
        fired_event.set()

    srv = WebhookTriggerServer(executor=fake_executor)
    srv.captured = captured  # type: ignore[attr-defined]
    srv.fired_event = fired_event  # type: ignore[attr-defined]
    yield srv
    srv.stop()


def _write_dummy_script(path):
    path.write_text('[["AC_screen_size"]]', encoding="utf-8")


def test_add_assigns_id_and_normalises_path(server):
    trigger = server.add(path="hooks/build", script_path="x.json")
    assert trigger.path == "/hooks/build"
    assert trigger.methods == ("POST",)
    assert len(trigger.webhook_id) == 8


def test_add_rejects_conflicting_path_and_method(server):
    server.add(path="/dup", script_path="a.json", methods=["POST"])
    with pytest.raises(ValueError):
        server.add(path="/dup", script_path="b.json", methods=["POST"])


def test_remove_returns_false_for_unknown(server):
    assert server.remove("nope") is False


def test_match_skips_disabled(server):
    trig = server.add(path="/p", script_path="s.json")
    assert server.match("/p", "POST") is trig
    server.set_enabled(trig.webhook_id, False)
    assert server.match("/p", "POST") is None


def test_authorize_uses_constant_time_compare(server):
    trig = server.add(path="/p", script_path="s.json", token="abc123")
    assert server.authorize(trig, "Bearer abc123") is True
    assert server.authorize(trig, "Bearer wrong") is False
    assert server.authorize(trig, None) is False


def test_authorize_no_token_allows_all(server):
    trig = server.add(path="/p", script_path="s.json", token=None)
    assert server.authorize(trig, None) is True


def test_post_fires_trigger_with_payload(server, tmp_path):
    script = tmp_path / "hook.json"
    _write_dummy_script(script)
    server.add(path="/jobs", script_path=str(script), methods=["POST"])
    host, port = server.start("127.0.0.1", 0)
    body = json.dumps({"hello": "world"}).encode("utf-8")
    status, _ = _post(
        _local_url(host, port, "/jobs?ref=main"),
        body=body,
        headers={"Content-Type": "application/json",
                 "X-Custom": "value"},
    )
    assert status == 200
    assert server.fired_event.wait(timeout=2.0)  # type: ignore[attr-defined]
    actions, variables = server.captured[0]  # type: ignore[attr-defined]
    assert actions == [["AC_screen_size"]]
    assert variables["webhook.method"] == "POST"
    assert variables["webhook.path"] == "/jobs"
    assert variables["webhook.query"] == {"ref": ["main"]}
    assert variables["webhook.body"] == body.decode()
    assert variables["webhook.json"] == {"hello": "world"}
    headers = variables["webhook.headers"]
    assert headers["x-custom"] == "value"


def test_unknown_path_returns_404(server):
    server.add(path="/known", script_path="x.json")
    host, port = server.start("127.0.0.1", 0)
    with pytest.raises(urllib.error.HTTPError) as excinfo:
        _post(_local_url(host, port, "/unknown"))
    assert excinfo.value.code == 404


def test_token_mismatch_returns_401(server, tmp_path):
    script = tmp_path / "hook.json"
    _write_dummy_script(script)
    server.add(path="/p", script_path=str(script), token="topsecret")
    host, port = server.start("127.0.0.1", 0)
    with pytest.raises(urllib.error.HTTPError) as excinfo:
        _post(
            _local_url(host, port, "/p"),
            headers={"Authorization": "Bearer wrong"},
        )
    assert excinfo.value.code == 401


def test_oversize_body_rejected(server, tmp_path):
    script = tmp_path / "hook.json"
    _write_dummy_script(script)
    server.add(path="/p", script_path=str(script))
    host, port = server.start("127.0.0.1", 0)
    payload = b"x" * (2 << 20)  # 2 MiB > 1 MiB cap
    with pytest.raises(urllib.error.HTTPError) as excinfo:
        _post(_local_url(host, port, "/p"), body=payload,
              headers={"Content-Type": "application/octet-stream"})
    assert excinfo.value.code in (413, 400)


def test_method_filter_rejects_other_verbs(server):
    server.add(path="/only-post", script_path="x.json", methods=["POST"])
    host, port = server.start("127.0.0.1", 0)
    with pytest.raises(urllib.error.HTTPError) as excinfo:
        _post(_local_url(host, port, "/only-post"), method="GET")
    assert excinfo.value.code == 404


def test_stop_is_idempotent(server):
    server.start("127.0.0.1", 0)
    server.stop()
    server.stop()
    assert server.is_running is False


def test_start_is_idempotent(server):
    first = server.start("127.0.0.1", 0)
    second = server.start("127.0.0.1", 0)
    assert first == second
