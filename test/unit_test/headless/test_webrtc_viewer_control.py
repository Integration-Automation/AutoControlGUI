"""What the viewer says to the host, and what it believes coming back.

The session half is in `test_webrtc_viewer_session.py`. This file covers the
control channel: the request verbs the GUI drives, and the dispatch table
that decides what an inbound envelope means.

The direction matters. On the host every inbound message is a boundary to be
refused; here every inbound message is a *claim by the host about this
session* -- that the token was accepted, that the session is read-only, that
the inbox holds these files -- and the viewer acts on it. So the tests below
are about the viewer believing exactly what it was told and no more:

* **`auth_ok` is what flips the session live**, and it carries both the
  read-only flag and the host's stable fingerprint in the same envelope.
  A fingerprint that arrives empty must not overwrite one already shown to
  the user, because that is the string they compared out-of-band.
* **`permissions` and `read_only` are two spellings of the same state.**
  The newer envelope carries five flags; the viewer only mirrors one of them
  (input), and a missing flag has to default to permitted, not to denied --
  the GUI greys out its own controls from this.
* **Every callback here is a Qt slot** reached from the asyncio thread, so
  each one is wrapped: a raising GUI must not take the DataChannel down.

`get_bridge` is replaced (from `headless._webrtc_doubles`) with one that
runs the callback inline; otherwise every `_send` would queue onto a loop no
test is running.
"""
from __future__ import annotations

import asyncio
import json

import pytest

from headless._webrtc_doubles import Bridge, Channel, MicSender
from je_auto_control.utils.remote_desktop import webrtc_viewer as viewer_module
from je_auto_control.utils.remote_desktop.webrtc_viewer import (
    WebRTCDesktopViewer,
)


@pytest.fixture(autouse=True)
def bridge(monkeypatch):
    fake = Bridge()
    monkeypatch.setattr(viewer_module, "get_bridge", lambda: fake)
    return fake


@pytest.fixture
def viewer():
    """A viewer with an open control channel, as after `_attach_datachannel`."""
    instance = WebRTCDesktopViewer(token="secret")
    channel = Channel()
    instance._control_channel = channel
    instance._wire_control_channel(channel)
    channel.sent.clear()          # drop the auth envelope the wiring may send
    return instance


def _sent(viewer_instance):
    return [json.loads(text) for text in viewer_instance._control_channel.sent]


def _deliver(viewer_instance, payload):
    viewer_instance._control_channel.fire("message", json.dumps(payload))


# --- outbound verbs -----------------------------------------------------------

def test_input_is_sent_as_a_payload_envelope(viewer):
    viewer.send_input({"kind": "mouse", "x": 3})
    assert _sent(viewer) == [{"type": "input",
                              "payload": {"kind": "mouse", "x": 3}}]


def test_the_input_payload_is_copied_not_referenced(viewer):
    payload = {"kind": "mouse"}
    viewer.send_input(payload)
    payload["kind"] = "mutated"
    assert _sent(viewer)[0]["payload"] == {"kind": "mouse"}


@pytest.mark.parametrize("method,expected", [
    ("request_send_sas", "send_sas"),
    ("request_inbox_listing", "list_inbox"),
    ("request_renegotiation", "renegotiate_request"),
])
def test_the_parameterless_verbs_each_send_their_envelope(viewer, method,
                                                          expected):
    getattr(viewer, method)()
    assert _sent(viewer) == [{"type": expected}]


def test_requesting_a_file_names_it(viewer):
    viewer.request_inbox_file("report.txt")
    assert _sent(viewer) == [{"type": "request_file", "name": "report.txt"}]


def test_deleting_a_file_names_it(viewer):
    viewer.delete_inbox_file("report.txt")
    assert _sent(viewer) == [{"type": "delete_inbox_file",
                              "name": "report.txt"}]


@pytest.mark.parametrize("method", ["request_inbox_file", "delete_inbox_file"])
def test_an_empty_name_is_refused_before_it_reaches_the_wire(viewer, method):
    with pytest.raises(ValueError, match="name required"):
        getattr(viewer, method)("")
    assert _sent(viewer) == []


def test_sending_before_the_channel_opens_is_dropped_not_raised(bridge):
    # The GUI can wire buttons up before the host's channel arrives; a click
    # in that window is a no-op, not a traceback in a Qt slot.
    WebRTCDesktopViewer(token="secret").send_input({"kind": "mouse"})
    assert bridge.deferred == []


def test_a_channel_that_fails_mid_send_does_not_raise(viewer):
    viewer._control_channel.send_error = OSError("channel closed")
    viewer.send_input({"kind": "mouse"})


def test_a_channel_closed_between_queue_and_send_is_a_no_op(viewer):
    viewer._control_channel = None
    viewer._safe_channel_send("{}")


def test_the_auth_envelope_omits_a_viewer_id_that_was_never_set(viewer):
    viewer._send_auth()
    assert _sent(viewer) == [{"type": "auth", "token": "secret"}]


# --- inbound envelopes: shape -------------------------------------------------

@pytest.mark.parametrize("message", [b"\x00", 42, None, ["auth_ok"]])
def test_a_non_text_message_is_ignored(viewer, message):
    viewer._control_channel.fire("message", message)
    assert viewer.authenticated is False


def test_a_malformed_envelope_is_dropped(viewer):
    viewer._control_channel.fire("message", "{not json")
    assert viewer.authenticated is False


def test_a_json_scalar_is_not_an_envelope(viewer):
    viewer._control_channel.fire("message", '"auth_ok"')
    assert viewer.authenticated is False


def test_an_unknown_message_type_is_ignored(viewer):
    _deliver(viewer, {"type": "shutdown"})
    assert viewer.authenticated is False


def test_closing_the_control_channel_ends_the_session(viewer):
    viewer._authenticated = True
    viewer._control_channel.fire("close")
    assert viewer.authenticated is False


# --- authentication result ----------------------------------------------------

def test_auth_ok_makes_the_session_live():
    seen = []
    viewer = WebRTCDesktopViewer(token="secret", on_auth_result=seen.append)
    viewer._control_channel = Channel()
    viewer._wire_control_channel(viewer._control_channel)
    _deliver(viewer, {"type": "auth_ok"})
    assert viewer.authenticated is True
    assert seen == [True]


def test_auth_ok_carries_the_read_only_flag(viewer):
    _deliver(viewer, {"type": "auth_ok", "read_only": True})
    assert viewer.read_only is True


def test_auth_ok_publishes_the_host_fingerprint():
    seen = []
    viewer = WebRTCDesktopViewer(token="secret", on_fingerprint=seen.append)
    viewer._control_channel = Channel()
    viewer._wire_control_channel(viewer._control_channel)
    _deliver(viewer, {"type": "auth_ok", "fingerprint": "AB:CD:EF"})
    assert viewer.host_fingerprint == "AB:CD:EF"
    assert seen == ["AB:CD:EF"]


def test_the_fingerprint_is_recorded_even_with_nobody_subscribed(viewer):
    # `host_fingerprint` is read by the GUI on demand as well as pushed, so
    # it has to be stored whether or not a callback was registered.
    _deliver(viewer, {"type": "auth_ok", "fingerprint": "AB:CD:EF"})
    assert viewer.host_fingerprint == "AB:CD:EF"


@pytest.mark.parametrize("fingerprint", [None, "", 42])
def test_an_absent_fingerprint_does_not_overwrite_the_one_on_screen(
        viewer, fingerprint):
    # It is the string the user compared out-of-band; a later envelope
    # without one must leave it standing rather than blank the field.
    viewer._host_fingerprint = "AB:CD:EF"
    _deliver(viewer, {"type": "auth_ok", "fingerprint": fingerprint})
    assert viewer.host_fingerprint == "AB:CD:EF"


def test_a_raising_fingerprint_callback_still_authenticates():
    def _boom(_value):
        raise RuntimeError("Qt widget already deleted")

    viewer = WebRTCDesktopViewer(token="secret", on_fingerprint=_boom)
    viewer._control_channel = Channel()
    viewer._wire_control_channel(viewer._control_channel)
    _deliver(viewer, {"type": "auth_ok", "fingerprint": "AB"})
    assert viewer.authenticated is True


def test_auth_fail_leaves_the_session_closed():
    seen = []
    viewer = WebRTCDesktopViewer(token="wrong", on_auth_result=seen.append)
    viewer._control_channel = Channel()
    viewer._wire_control_channel(viewer._control_channel)
    viewer._authenticated = True
    _deliver(viewer, {"type": "auth_fail"})
    assert viewer.authenticated is False
    assert seen == [False]


def test_an_auth_result_with_no_listener_is_survivable(viewer):
    _deliver(viewer, {"type": "auth_ok"})
    assert viewer.authenticated is True


def test_a_raising_auth_callback_does_not_break_the_channel():
    def _boom(_ok):
        raise RuntimeError("Qt widget already deleted")

    viewer = WebRTCDesktopViewer(token="secret", on_auth_result=_boom)
    viewer._control_channel = Channel()
    viewer._wire_control_channel(viewer._control_channel)
    _deliver(viewer, {"type": "auth_ok"})
    assert viewer.authenticated is True


# --- permission updates -------------------------------------------------------

def test_the_legacy_read_only_envelope_is_still_understood(viewer):
    _deliver(viewer, {"type": "read_only", "value": True})
    assert viewer.read_only is True
    _deliver(viewer, {"type": "read_only", "value": False})
    assert viewer.read_only is False


def test_a_read_only_envelope_with_no_value_means_not_read_only(viewer):
    viewer._read_only = True
    _deliver(viewer, {"type": "read_only"})
    assert viewer.read_only is False


def test_the_permissions_envelope_mirrors_the_input_flag(viewer):
    _deliver(viewer, {"type": "permissions", "value": {"allow_input": False}})
    assert viewer.read_only is True
    _deliver(viewer, {"type": "permissions", "value": {"allow_input": True}})
    assert viewer.read_only is False


def test_a_permissions_envelope_without_the_input_flag_assumes_permitted(
        viewer):
    # The GUI greys out its own controls from this; defaulting to denied
    # would lock the user out because a newer host sent a shorter dict.
    viewer._read_only = True
    _deliver(viewer, {"type": "permissions", "value": {"allow_files": True}})
    assert viewer.read_only is False


def test_a_permissions_envelope_that_is_not_a_dict_is_ignored(viewer):
    viewer._read_only = True
    _deliver(viewer, {"type": "permissions", "value": "read_only"})
    assert viewer.read_only is True


# --- the inbox listing --------------------------------------------------------

def test_an_inbox_listing_reaches_its_callback(viewer):
    seen = []
    viewer.set_inbox_listing_callback(seen.append)
    _deliver(viewer, {"type": "list_inbox_response",
                      "files": [{"name": "a.txt", "size": 1}]})
    assert seen == [[{"name": "a.txt", "size": 1}]]


def test_a_listing_with_no_files_key_becomes_an_empty_list(viewer):
    seen = []
    viewer.set_inbox_listing_callback(seen.append)
    _deliver(viewer, {"type": "list_inbox_response"})
    assert seen == [[]]


def test_a_listing_with_no_listener_is_dropped(viewer):
    _deliver(viewer, {"type": "list_inbox_response", "files": []})


def test_a_raising_listing_callback_is_contained(viewer):
    def _boom(_files):
        raise RuntimeError("Qt model already deleted")

    viewer.set_inbox_listing_callback(_boom)
    _deliver(viewer, {"type": "list_inbox_response", "files": []})


@pytest.mark.parametrize("msg_type", ["delete_inbox_response",
                                      "request_file_response"])
def test_an_inbox_operation_result_reaches_its_callback(viewer, msg_type):
    seen = []
    viewer.set_inbox_op_result_callback(
        lambda name, ok, error: seen.append((name, ok, error)),
    )
    _deliver(viewer, {"type": msg_type, "name": "a.txt", "ok": False,
                      "error": "not found"})
    assert seen == [("a.txt", False, "not found")]


def test_an_operation_result_defaults_to_a_failure(viewer):
    # A response missing its fields is not a success; the GUI would
    # otherwise report a delete that never happened.
    seen = []
    viewer.set_inbox_op_result_callback(
        lambda name, ok, error: seen.append((name, ok, error)),
    )
    _deliver(viewer, {"type": "delete_inbox_response"})
    assert seen == [("", False, None)]


def test_an_operation_result_with_no_listener_is_dropped(viewer):
    _deliver(viewer, {"type": "delete_inbox_response", "name": "a.txt"})


def test_a_raising_operation_callback_is_contained(viewer):
    def _boom(_name, _ok, _error):
        raise RuntimeError("Qt widget already deleted")

    viewer.set_inbox_op_result_callback(_boom)
    _deliver(viewer, {"type": "delete_inbox_response", "name": "a.txt"})


# --- host-initiated renegotiation ---------------------------------------------

def test_a_renegotiate_offer_without_a_connection_is_ignored(viewer):
    _deliver(viewer, {"type": "renegotiate_offer", "sdp": "v=0 offer"})
    assert viewer._background_tasks == set()


def test_a_renegotiate_offer_with_no_sdp_is_ignored(viewer):
    viewer._pc = object()
    _deliver(viewer, {"type": "renegotiate_offer", "sdp": None})
    assert viewer._background_tasks == set()


def test_a_renegotiate_offer_is_handled_on_the_event_loop(viewer, monkeypatch):
    applied = []

    class _Pc:
        transceivers = []

        async def setRemoteDescription(self, description):  # noqa: N802
            applied.append(description.sdp)

        def getTransceivers(self):      # noqa: N802  # reason: the aiortc name
            return []

        async def createAnswer(self):   # noqa: N802  # reason: the aiortc name
            return "answer"

        async def setLocalDescription(self, description):   # noqa: N802
            pass

        @property
        def localDescription(self):     # noqa: N802  # reason: the aiortc name
            return type("_Desc", (), {"sdp": "v=0 answer"})()

    async def _drive():
        viewer._pc = _Pc()
        _deliver(viewer, {"type": "renegotiate_offer", "sdp": "v=0 offer"})
        assert len(viewer._background_tasks) == 1
        await asyncio.gather(*viewer._background_tasks)

    async def _noop(pc, timeout=None):
        return None

    monkeypatch.setattr(viewer_module, "wait_for_ice_gathering", _noop)
    asyncio.run(_drive())
    assert applied == ["v=0 offer"]


# --- microphone uplink --------------------------------------------------------

@pytest.fixture
def mic_sender(monkeypatch):
    monkeypatch.setattr(
        "je_auto_control.utils.remote_desktop.webrtc_mic.MicUplinkSender",
        MicSender,
    )


def test_enabling_the_microphone_before_connecting_is_refused(viewer):
    with pytest.raises(RuntimeError, match="mic channel not open"):
        viewer.enable_mic_send()


def test_enabling_the_microphone_starts_one_sender(viewer, mic_sender):
    channel = Channel("mic")
    viewer._mic_channel = channel
    viewer.enable_mic_send()
    first = viewer._mic_sender
    assert first.started
    assert first.channel is channel
    assert viewer.mic_active is True
    viewer.enable_mic_send()
    assert viewer._mic_sender is first


def test_disabling_the_microphone_stops_it(viewer, mic_sender):
    viewer._mic_channel = Channel("mic")
    viewer.enable_mic_send()
    viewer.disable_mic_send()
    assert viewer._mic_sender is None
    assert viewer.mic_active is False


def test_disabling_a_microphone_that_was_never_enabled_is_a_no_op(viewer):
    viewer.disable_mic_send()
    assert viewer.mic_active is False


def test_a_microphone_that_fails_to_close_is_still_forgotten(viewer,
                                                             mic_sender):
    viewer._mic_channel = Channel("mic")
    viewer.enable_mic_send()
    viewer._mic_sender.stop_error = OSError("stream already closed")
    viewer.disable_mic_send()
    assert viewer._mic_sender is None


def test_a_sender_that_stopped_on_its_own_is_not_active(viewer, mic_sender):
    viewer._mic_channel = Channel("mic")
    viewer.enable_mic_send()
    viewer._mic_sender.running = False
    assert viewer.mic_active is False


# --- files --------------------------------------------------------------------

def test_sending_a_file_before_the_channel_opens_is_refused(viewer):
    with pytest.raises(RuntimeError, match="files channel not open"):
        viewer.send_file("C:/report.txt")


def test_sending_a_file_streams_it_over_the_files_channel(viewer, tmp_path):
    source = tmp_path / "notes.txt"
    source.write_bytes(b"hello")
    viewer._files_channel = Channel("files")
    viewer.send_file(str(source), remote_name="renamed.txt")
    envelope = json.loads(viewer._files_channel.sent[0])
    assert (envelope["type"], envelope["name"]) == ("file_begin",
                                                    "renamed.txt")


@pytest.fixture
def viewer_inbox(tmp_path, monkeypatch):
    """Point the viewer's inbox at tmp_path.

    The viewer takes no `inbox_dir` -- unlike the host it always uses
    `webrtc_files._DEFAULT_INBOX`, which is resolved at import time under
    the real `~/.je_auto_control`. Redirecting HOME would be too late.
    """
    from je_auto_control.utils.remote_desktop import webrtc_files
    inbox = tmp_path / "inbox"
    monkeypatch.setattr(webrtc_files, "_DEFAULT_INBOX", inbox)
    return inbox


def test_a_file_pushed_by_the_host_lands_and_is_announced(viewer,
                                                          viewer_inbox):
    seen = []
    viewer.set_file_received_callback(seen.append)
    channel = Channel("files")
    viewer._wire_files_channel(channel)
    inbox = viewer_inbox
    channel.fire("message", json.dumps({"type": "file_begin",
                                        "name": "pushed.txt", "size": 4}))
    channel.fire("message", b"data")
    channel.fire("message", json.dumps({"type": "file_end"}))
    assert (inbox / "pushed.txt").read_bytes() == b"data"
    assert seen and seen[0].name == "pushed.txt"


def test_a_file_arriving_with_no_listener_is_still_written(viewer,
                                                           viewer_inbox):
    channel = Channel("files")
    viewer._wire_files_channel(channel)
    channel.fire("message", json.dumps({"type": "file_begin",
                                        "name": "pushed.txt", "size": 1}))
    channel.fire("message", b"x")
    channel.fire("message", json.dumps({"type": "file_end"}))
    assert (viewer._files_receiver._inbox / "pushed.txt").exists()


def test_a_raising_file_callback_does_not_lose_the_file(viewer):
    def _boom(_path):
        raise RuntimeError("Qt widget already deleted")

    viewer.set_file_received_callback(_boom)
    viewer._on_viewer_file_done("C:/inbox/pushed.txt")


def test_the_files_receiver_is_built_once_and_reused(viewer, viewer_inbox):
    viewer._wire_files_channel(Channel("files"))
    first = viewer._files_receiver
    viewer._wire_files_channel(Channel("files"))
    assert viewer._files_receiver is first
