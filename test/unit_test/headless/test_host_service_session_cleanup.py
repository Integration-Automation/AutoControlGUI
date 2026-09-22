"""The host-service daemon must not leak a session per failed viewer attempt.

``run_service`` loops forever: mint an offer, publish it, wait up to 300 s for
an answer, connect. Any failure after the offer existed used to leave that
session registered, so an idle daemon gained one screen-source subscription
every five minutes for as long as it ran.
"""
import pytest

pytest.importorskip("aiortc")

from je_auto_control.utils.remote_desktop import host_service  # noqa: E402
from je_auto_control.utils.remote_desktop import signaling_client  # noqa: E402


class _Multi:
    def __init__(self):
        self.stopped = []
        self.accepted = []

    def create_session_offer(self):
        return "sid-1", "offer-sdp"

    def accept_session_answer(self, session_id, answer):
        self.accepted.append((session_id, answer))

    def stop_session(self, session_id):
        self.stopped.append(session_id)

    def session_count(self):
        return 1


def _config():
    return host_service.HostServiceConfig(
        token="t" * 16, server_url="http://127.0.0.1:1", host_id="h")


@pytest.mark.parametrize("failing", ["push_offer", "wait_for_answer"])
def test_a_failed_attempt_stops_its_session(monkeypatch, failing):
    monkeypatch.setattr(signaling_client, "push_offer", lambda *a, **k: None)
    monkeypatch.setattr(signaling_client, "wait_for_answer", lambda *a, **k: "answer")

    def boom(*_args, **_kwargs):
        raise TimeoutError("no answer within 300 s")

    monkeypatch.setattr(signaling_client, failing, boom)
    multi = _Multi()
    with pytest.raises(TimeoutError):
        host_service._serve_one_viewer(multi, _config())
    assert multi.stopped == ["sid-1"]


def test_a_successful_attempt_keeps_its_session(monkeypatch):
    monkeypatch.setattr(signaling_client, "push_offer", lambda *a, **k: None)
    monkeypatch.setattr(signaling_client, "wait_for_answer", lambda *a, **k: "answer")
    multi = _Multi()
    host_service._serve_one_viewer(multi, _config())
    assert multi.accepted == [("sid-1", "answer")]
    assert multi.stopped == []
