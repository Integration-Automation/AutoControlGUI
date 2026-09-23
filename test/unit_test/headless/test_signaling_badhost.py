"""The signaling server's pre-body guard cannot be sidestepped with a crafted Host.

Starlette up to 1.0.0 rebuilt ``request.url`` from the Host header, so a Host
of ``example.com?`` showed middleware another path than the router dispatched
(CVE-2026-48710, "BadHost"). The guard decides on ``scope["path"]``; with a
patched Starlette both give the same answer, and this pins that the guard
still stops an oversized body under a crafted Host.
"""
import pytest

pytest.importorskip("fastapi")
testclient = pytest.importorskip("fastapi.testclient")

from je_auto_control.utils.remote_desktop.signaling_server import create_app  # noqa: E402


def test_a_crafted_host_does_not_skip_the_body_limit():
    client = testclient.TestClient(create_app(shared_secret="s3cret", serve_web_viewer=False))
    body = b'{"sdp":"' + b"A" * (2 * 1024 * 1024) + b'"}'
    response = client.post("/sessions/host1/offer", content=body,
                           headers={"Content-Type": "application/json",
                                    "X-Signaling-Secret": "s3cret",
                                    "Host": "example.com?"})
    assert response.status_code == 413


def test_a_crafted_host_does_not_skip_the_secret_check():
    client = testclient.TestClient(create_app(shared_secret="s3cret", serve_web_viewer=False))
    response = client.get("/config/alice", headers={"Host": "example.com?"})
    assert response.status_code == 401
