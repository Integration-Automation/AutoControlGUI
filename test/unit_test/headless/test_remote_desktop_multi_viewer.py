"""One capture, N viewers: what the coordinator owns and what it delegates.

`MultiViewerHost` is deliberately thin -- it runs one `WebRTCDesktopHost`
per viewer and forwards almost everything -- but the four things it does
own are the ones that go wrong quietly:

* **The screen source is shared and reference-counted by hand.** It is
  built on the first session and stopped when the last one goes, so the
  capture thread outliving every viewer, or being torn down while one is
  still watching, are both bugs the tests below would catch.
* **Every callback is re-wrapped to carry a `session_id`.** The GUI gets
  `(session_id, state)` where the single-viewer host gives it `(state)`,
  and the pending-viewer wrapper has to look the host up *at fire time* --
  the viewer id it reports does not exist when the wrapper is built.
* **The connection timestamp is minted here, not in the host.** It is
  written from the auth wrapper, which is the only moment the coordinator
  is told a viewer got through.
* **A broadcast must not be stopped by one bad recipient.** `broadcast_file`
  skips viewers that never authenticated and keeps going past a viewer
  whose channel has died; the count it returns is what the GUI reports.

`WebRTCDesktopHost`, `ScreenVideoTrack` and `MediaRelay` are all replaced
here: this module is a coordinator, and every one of those three would drag
in a real PeerConnection or a real screen grab. What is *not* faked is the
session bookkeeping, which is the code under test.
"""
from __future__ import annotations

import pytest

from headless._webrtc_doubles import Track
from je_auto_control.utils.remote_desktop import multi_viewer as mv
from je_auto_control.utils.remote_desktop.multi_viewer import MultiViewerHost
from je_auto_control.utils.remote_desktop.permissions import SessionPermissions


class _FakeRelay:
    def __init__(self) -> None:
        self.subscribed = []

    def subscribe(self, track):
        proxy = ("proxy", len(self.subscribed))
        self.subscribed.append(track)
        return proxy


class _FakeHost:
    """A `WebRTCDesktopHost` stand-in that records what it was told."""

    instances = []

    def __init__(self, **kwargs) -> None:
        self.kwargs = kwargs
        self.authenticated = False
        self.connection_state = "new"
        self.pending_viewer_id = None
        self.offers = []
        self.answers = []
        self.pushed = []
        self.stopped = False
        self.permissions = None
        self.calls = []
        self.raise_on = set()
        self._pc = None
        _FakeHost.instances.append(self)

    def _maybe_raise(self, name: str) -> None:
        if name in self.raise_on:
            raise RuntimeError(f"{name} failed")

    def create_offer(self, peer_label="remote viewer"):
        self.offers.append(peer_label)
        return f"sdp-for-{peer_label}"

    def accept_answer(self, answer_sdp):
        self.answers.append(answer_sdp)

    def stop(self):
        self._maybe_raise("stop")
        self.stopped = True

    def approve_pending_viewer(self):
        self.calls.append("approve")

    def reject_pending_viewer(self):
        self.calls.append("reject")

    def trust_pending_viewer(self, label=""):
        self.calls.append(("trust", label))

    def set_permissions(self, permissions):
        self._maybe_raise("set_permissions")
        self.permissions = permissions

    def disable_accept_viewer_video(self):
        self._maybe_raise("disable_video")
        self.calls.append("disable_video")

    def disable_accept_viewer_audio_opus(self):
        self._maybe_raise("disable_audio")
        self.calls.append("disable_audio")

    def push_file(self, local_path, remote_name=None):
        self._maybe_raise("push_file")
        self.pushed.append((local_path, remote_name))


@pytest.fixture(autouse=True)
def fake_webrtc(monkeypatch):
    """Replace the three things that would touch a screen or a network."""
    _FakeHost.instances = []
    monkeypatch.setattr(mv, "WebRTCDesktopHost", _FakeHost)
    monkeypatch.setattr(mv, "ScreenVideoTrack", Track)
    monkeypatch.setattr(mv, "MediaRelay", _FakeRelay)
    yield
    _FakeHost.instances = []


def _host(**kwargs) -> MultiViewerHost:
    kwargs.setdefault("token", "shared-secret")
    return MultiViewerHost(**kwargs)


# --- construction -------------------------------------------------------------

def test_a_host_without_a_token_is_refused():
    with pytest.raises(ValueError, match="non-empty token"):
        MultiViewerHost(token="")


def test_read_only_shorthand_becomes_a_permission_set():
    assert _host(read_only=True).permissions.allow_input is False
    assert _host(read_only=False).permissions.allow_input is True


def test_explicit_permissions_win_over_the_shorthand():
    # Both arguments reach the GUI's constructor call; the granular one is
    # the newer surface and must not be overridden by a stale bool.
    permissions = SessionPermissions.from_read_only(False)
    host = _host(read_only=True, permissions=permissions)
    assert host.permissions is permissions


# --- session lifecycle --------------------------------------------------------

def test_first_session_builds_the_capture_and_labels_the_peer():
    host = _host()
    session_id, offer = host.create_session_offer()
    assert len(session_id) == 16, "secrets.token_hex(8)"
    assert offer == f"sdp-for-viewer-{session_id[:6]}"
    assert host.session_count() == 1
    assert isinstance(host.screen_track(), Track)


def test_every_session_subscribes_to_the_same_capture():
    host = _host()
    host.create_session_offer()
    host.create_session_offer()
    track = host.screen_track()
    tracks = [inst.kwargs["external_video_track"]
              for inst in _FakeHost.instances]
    assert len(set(tracks)) == 2, "each viewer gets its own relay proxy"
    assert all(t is not track for t in tracks)
    assert host.session_count() == 2


def test_the_capture_track_is_built_from_the_shared_config():
    from je_auto_control.utils.remote_desktop.webrtc_transport import (
        WebRTCConfig,
    )
    config = WebRTCConfig(monitor_index=2, fps=15, region=(1, 2, 3, 4),
                          show_cursor=False)
    host = _host(config=config)
    host.create_session_offer()
    assert host.screen_track().kwargs == {
        "monitor_index": 2, "fps": 15, "region": (1, 2, 3, 4),
        "show_cursor": False,
    }


def test_sessions_inherit_the_coordinator_settings():
    trust = object()
    host = _host(trust_list=trust, ip_whitelist=["10.0.0.1"])
    host.create_session_offer()
    kwargs = _FakeHost.instances[0].kwargs
    assert kwargs["token"] == "shared-secret"
    assert kwargs["trust_list"] is trust
    assert kwargs["ip_whitelist"] == ["10.0.0.1"]


def test_answers_go_to_the_session_they_belong_to():
    host = _host()
    first, _ = host.create_session_offer()
    second, _ = host.create_session_offer()
    host.accept_session_answer(second, "answer-sdp")
    by_id = dict(zip([first, second], _FakeHost.instances))
    assert by_id[second].answers == ["answer-sdp"]
    assert by_id[first].answers == []


def test_an_unknown_session_id_is_a_key_error():
    host = _host()
    with pytest.raises(KeyError, match="unknown session_id"):
        host.accept_session_answer("deadbeef", "answer")


def test_the_capture_survives_until_the_last_viewer_leaves():
    host = _host()
    first, _ = host.create_session_offer()
    second, _ = host.create_session_offer()
    track = host.screen_track()

    host.stop_session(first)
    assert not track.stopped, "one viewer is still watching"
    assert host.session_count() == 1

    host.stop_session(second)
    assert track.stopped
    assert host.screen_track() is None


def test_stopping_an_unknown_session_is_a_no_op():
    host = _host()
    host.create_session_offer()
    track = host.screen_track()
    host.stop_session("not-a-session")
    assert not track.stopped
    assert host.session_count() == 1


def test_a_session_that_fails_to_stop_is_still_forgotten():
    # The PeerConnection may already be dead when the GUI asks to close the
    # tab; the session must leave the table anyway, or the capture it holds
    # a reference to never gets released.
    host = _host()
    session_id, _ = host.create_session_offer()
    track = host.screen_track()
    _FakeHost.instances[0].raise_on.add("stop")
    host.stop_session(session_id)
    assert host.session_count() == 0
    assert track.stopped


def test_stop_all_tears_every_session_and_the_capture_down():
    host = _host()
    host.create_session_offer()
    host.create_session_offer()
    track = host.screen_track()
    host.stop_all()
    assert all(inst.stopped for inst in _FakeHost.instances)
    assert track.stopped
    assert host.session_count() == 0


def test_a_session_that_fails_to_stop_does_not_strand_the_others():
    host = _host()
    host.create_session_offer()
    host.create_session_offer()
    _FakeHost.instances[0].raise_on.add("stop")
    host.stop_all()
    assert _FakeHost.instances[1].stopped
    assert host.screen_track() is None, "the capture is still released"


def test_a_new_session_after_stop_all_builds_a_fresh_capture():
    host = _host()
    host.create_session_offer()
    first_track = host.screen_track()
    host.stop_all()
    host.create_session_offer()
    assert host.screen_track() is not first_track


# --- per-session controls -----------------------------------------------------

@pytest.mark.parametrize("method,recorded", [
    ("approve_pending_viewer", "approve"),
    ("reject_pending_viewer", "reject"),
])
def test_pending_viewer_decisions_reach_only_that_session(method, recorded):
    host = _host()
    first, _ = host.create_session_offer()
    host.create_session_offer()
    getattr(host, method)(first)
    assert _FakeHost.instances[0].calls == [recorded]
    assert _FakeHost.instances[1].calls == []


def test_trusting_a_viewer_carries_the_label_through():
    host = _host()
    session_id, _ = host.create_session_offer()
    host.trust_pending_viewer(session_id, label="Ops laptop")
    assert _FakeHost.instances[0].calls == [("trust", "Ops laptop")]


def test_pending_viewer_id_is_read_from_the_live_session():
    host = _host()
    session_id, _ = host.create_session_offer()
    _FakeHost.instances[0].pending_viewer_id = "viewer-7"
    assert host.pending_viewer_id(session_id) == "viewer-7"


# --- permissions --------------------------------------------------------------

def test_permissions_propagate_to_live_sessions_and_to_the_next_one():
    host = _host()
    host.create_session_offer()
    permissions = SessionPermissions.from_read_only(True)
    host.set_permissions(permissions)
    assert _FakeHost.instances[0].permissions is permissions
    host.create_session_offer()
    assert _FakeHost.instances[1].kwargs["permissions"] is permissions


def test_set_read_only_is_the_shorthand_for_the_same_thing():
    host = _host()
    host.create_session_offer()
    host.set_read_only(True)
    assert host.permissions.allow_input is False
    assert _FakeHost.instances[0].permissions.allow_input is False


def test_one_dead_session_does_not_block_the_permission_broadcast():
    host = _host()
    host.create_session_offer()
    host.create_session_offer()
    _FakeHost.instances[0].raise_on.add("set_permissions")
    host.set_read_only(True)
    assert _FakeHost.instances[1].permissions is not None


@pytest.mark.parametrize("method,recorded", [
    ("disable_accept_viewer_video", "disable_video"),
    ("disable_accept_viewer_audio_opus", "disable_audio"),
])
def test_disabling_an_inbound_slot_hits_every_session(method, recorded):
    host = _host()
    host.create_session_offer()
    host.create_session_offer()
    getattr(host, method)()
    assert all(inst.calls == [recorded] for inst in _FakeHost.instances)


@pytest.mark.parametrize("method,failure", [
    ("disable_accept_viewer_video", "disable_video"),
    ("disable_accept_viewer_audio_opus", "disable_audio"),
])
def test_disabling_a_slot_survives_a_session_that_is_already_gone(method,
                                                                 failure):
    host = _host()
    host.create_session_offer()
    host.create_session_offer()
    _FakeHost.instances[0].raise_on.add(failure)
    getattr(host, method)()
    assert _FakeHost.instances[1].calls, "the live session still got it"


# --- broadcast ----------------------------------------------------------------

def test_broadcast_reaches_only_authenticated_viewers():
    host = _host()
    host.create_session_offer()
    host.create_session_offer()
    _FakeHost.instances[0].authenticated = True
    assert host.broadcast_file("C:/report.txt", remote_name="r.txt") == 1
    assert _FakeHost.instances[0].pushed == [("C:/report.txt", "r.txt")]
    assert _FakeHost.instances[1].pushed == []


def test_broadcast_counts_the_viewers_that_actually_took_the_file():
    host = _host()
    host.create_session_offer()
    host.create_session_offer()
    for inst in _FakeHost.instances:
        inst.authenticated = True
    _FakeHost.instances[0].raise_on.add("push_file")
    assert host.broadcast_file("C:/report.txt") == 1


def test_broadcast_with_no_sessions_sends_nothing():
    assert _host().broadcast_file("C:/report.txt") == 0


# --- introspection ------------------------------------------------------------

def test_list_sessions_reports_live_state_per_viewer():
    host = _host()
    session_id, _ = host.create_session_offer()
    inst = _FakeHost.instances[0]
    inst.authenticated = True
    inst.connection_state = "connected"
    inst.pending_viewer_id = "viewer-1"
    [row] = host.list_sessions()
    assert row["session_id"] == session_id
    assert row["authenticated"] is True
    assert row["state"] == "connected"
    assert row["pending_viewer_id"] == "viewer-1"
    assert row["connected_at"] is None, "nobody has authenticated yet"


def test_screen_track_is_none_before_any_viewer_arrives():
    assert _host().screen_track() is None


def test_first_session_pc_skips_sessions_that_have_no_connection_yet():
    host = _host()
    host.create_session_offer()
    host.create_session_offer()
    pc = object()
    _FakeHost.instances[1]._pc = pc
    assert host.first_session_pc() is pc


def test_first_session_pc_is_none_when_nothing_is_connected():
    host = _host()
    host.create_session_offer()
    assert host.first_session_pc() is None


def test_session_pc_addresses_one_named_session():
    host = _host()
    first, _ = host.create_session_offer()
    second, _ = host.create_session_offer()
    pc = object()
    _FakeHost.instances[1]._pc = pc
    assert host.session_pc(second) is pc
    assert host.session_pc(first) is None


def test_session_pc_of_a_closed_session_is_none_rather_than_an_error():
    # The GUI polls this on a timer; a viewer that left between two ticks
    # must not raise out of the timer slot.
    assert _host().session_pc("gone") is None


# --- callback wrappers --------------------------------------------------------

def _fire(host_instance, key):
    """Invoke the wrapper the coordinator handed to one fake session."""
    host_instance.kwargs[key]()


def test_state_changes_are_reported_with_their_session_id():
    seen = []
    host = _host(on_session_state=lambda sid, state: seen.append((sid, state)))
    session_id, _ = host.create_session_offer()
    _FakeHost.instances[0].kwargs["on_state_change"]("connected")
    assert seen == [(session_id, "connected")]


def test_no_state_callback_means_no_wrapper_is_installed():
    # The single-viewer host checks this for None before calling it, so
    # handing it a wrapper that calls nothing would only cost work.
    host = _host()
    host.create_session_offer()
    assert _FakeHost.instances[0].kwargs["on_state_change"] is None


def test_authentication_stamps_the_connection_time_and_notifies():
    seen = []
    host = _host(on_session_authenticated=seen.append)
    session_id, _ = host.create_session_offer()
    _fire(_FakeHost.instances[0], "on_authenticated")
    assert seen == [session_id]
    [row] = host.list_sessions()
    assert row["connected_at"], "an ISO timestamp minted at auth time"


def test_the_connection_time_is_stamped_even_without_a_listener():
    # `list_sessions` reports it to the GUI table regardless of whether
    # anyone subscribed to the event, so the wrapper is always installed.
    host = _host()
    host.create_session_offer()
    _fire(_FakeHost.instances[0], "on_authenticated")
    assert host.list_sessions()[0]["connected_at"]


def test_a_pending_viewer_is_reported_with_the_id_read_at_fire_time():
    seen = []
    host = _host(on_pending_viewer=lambda sid, vid: seen.append((sid, vid)))
    session_id, _ = host.create_session_offer()
    # The id does not exist when the wrapper is built -- only when a viewer
    # actually knocks -- so the wrapper has to look the host up on each call.
    _FakeHost.instances[0].pending_viewer_id = "viewer-9"
    _fire(_FakeHost.instances[0], "on_pending_viewer")
    assert seen == [(session_id, "viewer-9")]


def test_a_pending_viewer_from_a_session_that_just_left_reports_none():
    seen = []
    host = _host(on_pending_viewer=lambda sid, vid: seen.append((sid, vid)))
    session_id, _ = host.create_session_offer()
    wrapper = _FakeHost.instances[0].kwargs["on_pending_viewer"]
    host.stop_session(session_id)
    wrapper()
    assert seen == [(session_id, None)]


def test_no_pending_callback_means_no_wrapper_is_installed():
    host = _host()
    host.create_session_offer()
    assert _FakeHost.instances[0].kwargs["on_pending_viewer"] is None


@pytest.mark.parametrize("kwarg,wrapper_key", [
    ("on_session_state", "on_state_change"),
    ("on_session_authenticated", "on_authenticated"),
    ("on_pending_viewer", "on_pending_viewer"),
])
def test_a_raising_gui_callback_never_reaches_the_session(kwarg, wrapper_key):
    # These fire on the asyncio thread; an exception escaping one of them
    # would kill the event loop that every other session shares.
    def _boom(*_args):
        raise RuntimeError("Qt widget already deleted")

    host = _host(**{kwarg: _boom})
    host.create_session_offer()
    wrapper = _FakeHost.instances[0].kwargs[wrapper_key]
    if wrapper_key == "on_state_change":
        wrapper("connected")
    else:
        wrapper()
