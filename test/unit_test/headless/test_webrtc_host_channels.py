"""What a connected viewer can make the host do, and what it cannot.

The session setup is in `test_webrtc_host_session.py`; this file is about
the four DataChannels that ride on it, and it is mostly about refusal. Every
message here arrives from the other end of the wire, so each handler is a
boundary with the same three questions behind it:

* **Has this viewer authenticated?** The channels open with the
  PeerConnection, which is *before* the token is checked -- so a peer that
  never authenticates can still push bytes at every one of them.
* **Do the session permissions allow it?** `read_only` is a shorthand over
  five flags the operator can flip mid-session from the GUI, and each
  channel consults a different one: input, files, audio.
* **Is it flooding?** The token buckets exist for a viewer that is
  authenticated and permitted and still sending 10,000 events a second.

The inbox handlers get the most attention because they are the ones that
take a *name* from the viewer and turn it into a path on the host's disk.
`_safe_basename` is what stands between `../../.ssh/authorized_keys` and the
host's home directory, and these tests pin down that the host actually
routes through it -- on the listing, the fetch and the delete alike.

`get_bridge` and the audit log are replaced (from
`headless._webrtc_doubles`): the first would queue work onto a loop no test
is running, the second writes to the real `~/.je_auto_control`.
"""
from __future__ import annotations

import asyncio
import json

import pytest

from headless._webrtc_doubles import (
    AuditLog, Bridge, Channel, FakePeerConnection, MicReceiver,
)
from je_auto_control.utils.remote_desktop import webrtc_host as host_module
from je_auto_control.utils.remote_desktop.permissions import SessionPermissions
from je_auto_control.utils.remote_desktop.rate_limit import RateLimitConfig
from je_auto_control.utils.remote_desktop.webrtc_host import WebRTCDesktopHost


@pytest.fixture(autouse=True)
def bridge(monkeypatch):
    fake = Bridge()
    monkeypatch.setattr(host_module, "get_bridge", lambda: fake)
    return fake


@pytest.fixture(autouse=True)
def audit_log(monkeypatch):
    log = AuditLog()
    monkeypatch.setattr(host_module, "default_audit_log", lambda: log)
    return log


@pytest.fixture
def host(tmp_path):
    """An authenticated host with a control channel, and an empty inbox."""
    instance = WebRTCDesktopHost(token="secret", inbox_dir=tmp_path / "inbox")
    channel = Channel()
    instance._control_channel = channel
    instance._wire_control_channel(channel)
    instance._authenticated = True
    return instance


def _sent(host_instance):
    return [json.loads(text) for text in host_instance._control_channel.sent]


def _deliver(host_instance, payload):
    host_instance._control_channel.fire("message", json.dumps(payload))


def _revoke_files(host_instance):
    """Drop to read-only, then forget the permissions envelope that sends."""
    host_instance.set_read_only(True)
    host_instance._control_channel.sent.clear()


# --- the control envelope -----------------------------------------------------

@pytest.mark.parametrize("message", [
    b"\x00\x01", 42, None, ["input"],
])
def test_a_non_text_control_message_is_ignored(host, message):
    # The ctrl channel is text-only; binary on it is either a bug at the
    # other end or someone probing.
    host._control_channel.fire("message", message)
    assert _sent(host) == []


def test_a_malformed_envelope_is_dropped(host):
    host._control_channel.fire("message", "{not json")
    assert _sent(host) == []


def test_a_json_scalar_is_not_an_envelope(host):
    host._control_channel.fire("message", '"input"')
    assert _sent(host) == []


def test_an_unknown_message_type_is_ignored(host):
    _deliver(host, {"type": "reboot_the_machine"})
    assert _sent(host) == []


def test_an_envelope_with_no_type_is_ignored(host):
    _deliver(host, {"payload": {"kind": "mouse"}})
    assert _sent(host) == []


def test_an_unauthenticated_peer_can_only_send_auth():
    host = WebRTCDesktopHost(token="secret")
    channel = Channel()
    host._control_channel = channel
    host._wire_control_channel(channel)
    dispatched = []
    host._dispatch = dispatched.append
    _deliver(host, {"type": "input", "payload": {"kind": "mouse"}})
    assert dispatched == [], "input before auth is not input, it is noise"


def test_an_unauthenticated_peer_reaches_the_token_check():
    host = WebRTCDesktopHost(token="secret")
    channel = Channel()
    host._control_channel = channel
    host._wire_control_channel(channel)
    _deliver(host, {"type": "auth", "token": "secret"})
    assert host.authenticated is True


def test_the_control_channel_open_event_is_survivable(host):
    host._control_channel.fire("open")


def test_closing_the_control_channel_ends_the_session(host):
    host._control_channel.fire("close")
    assert host.authenticated is False


# --- input --------------------------------------------------------------------

def test_input_reaches_the_dispatcher(host):
    dispatched = []
    host._dispatch = dispatched.append
    _deliver(host, {"type": "input", "payload": {"kind": "mouse", "x": 3}})
    assert dispatched == [{"kind": "mouse", "x": 3}]


def test_input_is_refused_in_read_only_mode(host):
    dispatched = []
    host._dispatch = dispatched.append
    host.set_read_only(True)
    _deliver(host, {"type": "input", "payload": {"kind": "mouse"}})
    assert dispatched == []


def test_a_payload_that_is_not_a_dict_never_reaches_the_dispatcher(host):
    dispatched = []
    host._dispatch = dispatched.append
    _deliver(host, {"type": "input", "payload": "click"})
    assert dispatched == []


def test_a_failing_dispatch_does_not_kill_the_channel(host):
    # `dispatch_input` raises the whole AutoControl exception family plus
    # OSError; anything escaping here would take the DataChannel bridge with
    # it and end the session over one bad event.
    def _boom(_payload):
        raise ValueError("unknown key name")

    host._dispatch = _boom
    _deliver(host, {"type": "input", "payload": {"kind": "key"}})
    _deliver(host, {"type": "input", "payload": {"kind": "key"}})


def test_a_flood_of_input_is_dropped_and_audited(audit_log):
    host = WebRTCDesktopHost(
        token="secret", rate_limit=RateLimitConfig(input_burst=0),
    )
    channel = Channel()
    host._control_channel = channel
    host._wire_control_channel(channel)
    host._authenticated = True
    dispatched = []
    host._dispatch = dispatched.append
    _deliver(host, {"type": "input", "payload": {"kind": "mouse"}})
    assert dispatched == []
    assert [event for event, _ in audit_log.events] == ["rate_limit_input"]


def test_the_flood_audit_entry_is_written_once_per_window(audit_log):
    # One log line per five-second window, not one per dropped event --
    # otherwise the flood is mirrored straight into the audit log.
    host = WebRTCDesktopHost(
        token="secret", rate_limit=RateLimitConfig(input_burst=0),
    )
    channel = Channel()
    host._control_channel = channel
    host._wire_control_channel(channel)
    host._authenticated = True
    host._dispatch = lambda payload: None
    for _ in range(5):
        _deliver(host, {"type": "input", "payload": {"kind": "mouse"}})
    assert len(audit_log.events) == 1


def test_an_audit_log_that_cannot_be_written_does_not_break_the_drop(
        audit_log):
    audit_log.error = OSError("disk full")
    host = WebRTCDesktopHost(
        token="secret", rate_limit=RateLimitConfig(input_burst=0),
    )
    channel = Channel()
    host._control_channel = channel
    host._wire_control_channel(channel)
    host._authenticated = True
    host._dispatch = lambda payload: None
    _deliver(host, {"type": "input", "payload": {"kind": "mouse"}})


# --- the secure attention sequence --------------------------------------------

def test_send_sas_is_refused_in_read_only_mode(host, monkeypatch):
    called = []
    monkeypatch.setattr(
        "je_auto_control.utils.remote_desktop.session_actions"
        ".send_secure_attention_sequence",
        lambda: called.append(1),
    )
    host.set_read_only(True)
    _deliver(host, {"type": "send_sas"})
    assert called == []


def test_send_sas_reaches_the_platform_call_when_permitted(host, monkeypatch):
    called = []
    monkeypatch.setattr(
        "je_auto_control.utils.remote_desktop.session_actions"
        ".send_secure_attention_sequence",
        lambda: called.append(1),
    )
    _deliver(host, {"type": "send_sas"})
    assert called == [1]
    assert _sent(host)[-1]["type"] == "sas_ok"


# --- annotations --------------------------------------------------------------

def test_an_annotation_reaches_the_gui_callback():
    seen = []
    host = WebRTCDesktopHost(token="secret", on_annotation=seen.append)
    channel = Channel()
    host._control_channel = channel
    host._wire_control_channel(channel)
    host._authenticated = True
    _deliver(host, {"type": "annotate", "shape": "arrow"})
    assert seen == [{"type": "annotate", "shape": "arrow"}]


def test_an_annotation_with_no_listener_is_dropped(host):
    _deliver(host, {"type": "annotate", "shape": "arrow"})


def test_a_raising_annotation_callback_is_contained():
    def _boom(_data):
        raise RuntimeError("Qt widget already deleted")

    host = WebRTCDesktopHost(token="secret", on_annotation=_boom)
    channel = Channel()
    host._control_channel = channel
    host._wire_control_channel(channel)
    host._authenticated = True
    _deliver(host, {"type": "annotate"})


# --- renegotiation ------------------------------------------------------------

def test_a_renegotiate_answer_without_a_connection_is_ignored(host):
    _deliver(host, {"type": "renegotiate_answer", "sdp": "v=0\r\nanswer"})
    assert host._background_tasks == set()


def test_a_renegotiate_answer_with_no_sdp_is_ignored(host):
    host._pc = object()
    _deliver(host, {"type": "renegotiate_answer", "sdp": None})
    assert host._background_tasks == set()


def test_a_renegotiate_answer_is_applied_on_the_event_loop(host):
    pc = FakePeerConnection()

    async def _drive():
        host._pc = pc
        _deliver(host, {"type": "renegotiate_answer", "sdp": "v=0 answer"})
        # The handler runs on the DataChannel callback; applying the answer
        # is awaited work, so it is spawned rather than run inline.
        assert len(host._background_tasks) == 1
        await asyncio.gather(*host._background_tasks)

    asyncio.run(_drive())
    assert [d.sdp for d in pc.remote_descriptions] == ["v=0 answer"]


def test_applying_a_renegotiate_answer_resubscribes_the_viewer_media(host):
    pc = FakePeerConnection()
    host._pc = pc
    asyncio.run(host._async_apply_renegotiate_answer("v=0\r\nanswer"))
    assert [d.sdp for d in pc.remote_descriptions] == ["v=0\r\nanswer"]


def test_a_renegotiate_answer_that_aiortc_rejects_is_logged_not_raised(host):
    pc = FakePeerConnection()
    pc.remote_description_error = RuntimeError("invalid SDP")
    host._pc = pc
    asyncio.run(host._async_apply_renegotiate_answer("v=0\r\nnonsense"))


def test_applying_an_answer_without_a_connection_is_a_no_op(host):
    asyncio.run(host._async_apply_renegotiate_answer("v=0\r\nanswer"))


# --- the mic channel ----------------------------------------------------------

def _wire_mic(host_instance):
    channel = Channel("mic")
    host_instance._wire_mic_channel(channel)
    return channel


def test_mic_chunks_reach_the_receiver(host):
    receiver = MicReceiver()
    host._mic_receiver = receiver
    channel = _wire_mic(host)
    channel.fire("message", b"pcm")
    assert receiver.chunks == [b"pcm"]


def test_mic_chunks_are_dropped_before_authentication(host):
    receiver = MicReceiver()
    host._mic_receiver = receiver
    host._authenticated = False
    _wire_mic(host).fire("message", b"pcm")
    assert receiver.chunks == []


def test_mic_chunks_are_dropped_when_nobody_is_listening(host):
    # The channel exists from the moment the PeerConnection does; the
    # receiver only exists once the operator turned the mic on.
    _wire_mic(host).fire("message", b"pcm")


def test_mic_chunks_are_dropped_when_audio_is_not_permitted(host):
    receiver = MicReceiver()
    host._mic_receiver = receiver
    host.set_permissions(SessionPermissions.none())
    _wire_mic(host).fire("message", b"pcm")
    assert receiver.chunks == []


def test_enabling_mic_receive_starts_one_receiver(host, monkeypatch):
    monkeypatch.setattr(
        "je_auto_control.utils.remote_desktop.webrtc_mic.MicUplinkReceiver",
        MicReceiver,
    )
    host.enable_mic_receive()
    first = host._mic_receiver
    host.enable_mic_receive()
    assert host._mic_receiver is first
    assert first.started


def test_disabling_mic_receive_stops_it(host):
    receiver = MicReceiver()
    host._mic_receiver = receiver
    host.disable_mic_receive()
    assert receiver.stopped
    assert host._mic_receiver is None


def test_disabling_a_mic_that_was_never_enabled_is_a_no_op(host):
    host.disable_mic_receive()
    assert host._mic_receiver is None


def test_a_mic_that_fails_to_close_is_still_forgotten(host):
    receiver = MicReceiver()
    receiver.stop_error = OSError("stream already closed")
    host._mic_receiver = receiver
    host.disable_mic_receive()
    assert host._mic_receiver is None


# --- the files channel --------------------------------------------------------

def _file_begin(name="report.txt", size=4):
    return json.dumps({"type": "file_begin", "name": name, "size": size})


def test_an_incoming_file_lands_in_the_inbox(host):
    channel = Channel("files")
    host._wire_files_channel(channel)
    channel.fire("message", _file_begin())
    channel.fire("message", b"data")
    channel.fire("message", json.dumps({"type": "file_end"}))
    assert (host._files_receiver._inbox / "report.txt").read_bytes() == b"data"


def test_an_unauthenticated_peer_cannot_write_to_the_inbox(host):
    host._authenticated = False
    channel = Channel("files")
    host._wire_files_channel(channel)
    channel.fire("message", _file_begin())
    channel.fire("message", b"data")
    assert list(host._files_receiver._inbox.iterdir()) == []


def test_a_viewer_without_file_permission_cannot_write_to_the_inbox(host):
    host.set_read_only(True)
    channel = Channel("files")
    host._wire_files_channel(channel)
    channel.fire("message", _file_begin())
    assert list(host._files_receiver._inbox.iterdir()) == []


def test_a_flood_of_transfers_is_dropped_and_audited(audit_log, tmp_path):
    host = WebRTCDesktopHost(
        token="secret", inbox_dir=tmp_path / "inbox",
        rate_limit=RateLimitConfig(files_burst=0),
    )
    host._authenticated = True
    channel = Channel("files")
    host._wire_files_channel(channel)
    channel.fire("message", _file_begin())
    assert list(host._files_receiver._inbox.iterdir()) == []
    assert [event for event, _ in audit_log.events] == ["rate_limit_files"]


def test_chunks_of_an_allowed_transfer_are_not_rate_limited(tmp_path):
    # The bucket counts transfers, not bytes: a file already accepted must
    # not stall halfway through because its chunks exhausted the same
    # bucket its envelope came out of.
    host = WebRTCDesktopHost(
        token="secret", inbox_dir=tmp_path / "inbox",
        rate_limit=RateLimitConfig(files_per_minute=60.0, files_burst=1),
    )
    host._authenticated = True
    channel = Channel("files")
    host._wire_files_channel(channel)
    channel.fire("message", _file_begin(size=6))
    for chunk in (b"ab", b"cd", b"ef"):
        channel.fire("message", chunk)
    channel.fire("message", json.dumps({"type": "file_end"}))
    assert (host._files_receiver._inbox / "report.txt").read_bytes() == b"abcdef"


def test_the_transfer_flood_audit_entry_is_written_once_per_window(audit_log,
                                                                   tmp_path):
    # Same rule as the input bucket: one line per five-second window, not
    # one per refused transfer.
    host = WebRTCDesktopHost(
        token="secret", inbox_dir=tmp_path / "inbox",
        rate_limit=RateLimitConfig(files_burst=0),
    )
    host._authenticated = True
    channel = Channel("files")
    host._wire_files_channel(channel)
    for _ in range(4):
        channel.fire("message", _file_begin())
    assert len(audit_log.events) == 1


def test_a_completed_transfer_is_audited_and_announced(host, audit_log):
    seen = []
    host.set_file_received_callback(seen.append)
    channel = Channel("files")
    host._wire_files_channel(channel)
    channel.fire("message", _file_begin())
    channel.fire("message", b"data")
    channel.fire("message", json.dumps({"type": "file_end"}))
    assert [event for event, _ in audit_log.events] == ["file_received"]
    assert seen and seen[0].name == "report.txt"


def test_a_raising_file_callback_does_not_lose_the_file(host):
    def _boom(_path):
        raise RuntimeError("Qt widget already deleted")

    host.set_file_received_callback(_boom)
    host._on_file_done(host._inbox_dir)


def test_an_audit_failure_still_lets_the_callback_run(host, audit_log):
    audit_log.error = OSError("disk full")
    seen = []
    host.set_file_received_callback(seen.append)
    host._on_file_done("C:/inbox/report.txt")
    assert seen == ["C:/inbox/report.txt"]


def test_pushing_a_file_before_a_viewer_connects_is_refused(host):
    host._files_channel = None
    with pytest.raises(RuntimeError, match="not connected"):
        host.push_file("C:/report.txt")


def test_pushing_a_file_to_an_unauthenticated_peer_is_refused(host):
    host._files_channel = Channel("files")
    host._authenticated = False
    with pytest.raises(RuntimeError, match="not connected"):
        host.push_file("C:/report.txt")


def test_pushing_a_file_streams_it_over_the_files_channel(host, tmp_path):
    source = tmp_path / "notes.txt"
    source.write_bytes(b"hello")
    host._files_channel = Channel("files")
    host.push_file(str(source), remote_name="renamed.txt")
    envelope = json.loads(host._files_channel.sent[0])
    assert envelope["type"] == "file_begin"
    assert envelope["name"] == "renamed.txt"


# --- the usb channel ----------------------------------------------------------

def test_the_usb_channel_is_gated_on_auth_and_the_global_opt_in(host,
                                                                monkeypatch):
    channel = Channel("usb")
    host._wire_usb_channel(channel)
    gate = host._usb_host._enabled

    monkeypatch.setattr(
        "je_auto_control.utils.usb.passthrough.is_usb_passthrough_enabled",
        lambda: False,
    )
    assert gate() is False, "authenticated is not enough; it is opt-in"

    monkeypatch.setattr(
        "je_auto_control.utils.usb.passthrough.is_usb_passthrough_enabled",
        lambda: True,
    )
    assert gate() is True

    host._authenticated = False
    assert gate() is False, "the opt-in is not enough either"


def test_the_usb_session_is_built_with_a_default_deny_acl(host, monkeypatch):
    import je_auto_control.utils.usb.passthrough as passthrough

    built = {}

    def _session(backend, acl=None, viewer_id=None):
        built.update(backend=backend, acl=acl, viewer_id=viewer_id)
        return "session"

    monkeypatch.setattr(passthrough, "UsbPassthroughSession", _session)
    monkeypatch.setattr(passthrough, "default_passthrough_backend",
                        lambda: "backend")
    channel = Channel("usb")
    host._viewer_id = "viewer-3"
    host._wire_usb_channel(channel)
    assert host._usb_host._factory() == "session"
    assert built["backend"] == "backend"
    assert built["viewer_id"] == "viewer-3"
    assert built["acl"] is not None, "never an unrestricted session"


# --- the inbox listing --------------------------------------------------------

def _inbox(host_instance):
    return host_instance._ensure_files_receiver()._inbox


def test_listing_the_inbox_reports_name_size_and_mtime(host):
    (_inbox(host) / "a.txt").write_bytes(b"12345")
    _deliver(host, {"type": "list_inbox"})
    [response] = _sent(host)
    assert response["type"] == "list_inbox_response"
    [entry] = response["files"]
    assert entry["name"] == "a.txt"
    assert entry["size"] == 5
    assert "mtime" in entry


def test_listing_the_inbox_skips_directories(host):
    (_inbox(host) / "sub").mkdir()
    (_inbox(host) / "a.txt").write_bytes(b"1")
    _deliver(host, {"type": "list_inbox"})
    assert [f["name"] for f in _sent(host)[0]["files"]] == ["a.txt"]


def test_listing_the_inbox_without_file_permission_is_refused(host):
    (_inbox(host) / "a.txt").write_bytes(b"1")
    _revoke_files(host)
    _deliver(host, {"type": "list_inbox"})
    [response] = _sent(host)
    assert response["files"] == []
    assert response["error"] == "files not permitted"


def test_an_unreadable_inbox_is_reported_as_an_error(host, monkeypatch):
    receiver = host._ensure_files_receiver()
    monkeypatch.setattr(
        type(receiver._inbox), "iterdir",
        lambda self: (_ for _ in ()).throw(OSError("permission denied")),
    )
    _deliver(host, {"type": "list_inbox"})
    [response] = _sent(host)
    assert response["files"] == []
    assert "permission denied" in response["error"]


def test_the_inbox_receiver_is_built_once_and_reused(host):
    assert host._ensure_files_receiver() is host._ensure_files_receiver()


# --- fetching a file back -----------------------------------------------------

def test_requesting_a_file_pushes_it_over_the_files_channel(host):
    (_inbox(host) / "a.txt").write_bytes(b"12345")
    host._files_channel = Channel("files")
    _deliver(host, {"type": "request_file", "name": "a.txt"})
    envelope = json.loads(host._files_channel.sent[0])
    assert (envelope["type"], envelope["name"]) == ("file_begin", "a.txt")


def test_requesting_a_missing_file_is_answered_not_ignored(host):
    _deliver(host, {"type": "request_file", "name": "gone.txt"})
    [response] = _sent(host)
    assert response == {"type": "request_file_response", "name": "gone.txt",
                        "ok": False, "error": "not found"}


def test_requesting_a_path_cannot_escape_the_inbox(host, tmp_path):
    # The name arrives from the viewer; `..` in it must resolve to a
    # basename inside the inbox rather than to the host's own files.
    outside = tmp_path / "secret.txt"
    outside.write_bytes(b"private")
    _deliver(host, {"type": "request_file", "name": "../secret.txt"})
    [response] = _sent(host)
    assert response["ok"] is False
    assert response["name"] == "secret.txt", "sanitized to a bare basename"


def test_requesting_a_file_without_permission_is_silently_refused(host):
    (_inbox(host) / "a.txt").write_bytes(b"1")
    _revoke_files(host)
    _deliver(host, {"type": "request_file", "name": "a.txt"})
    assert _sent(host) == []


def test_a_request_with_a_non_string_name_is_ignored(host):
    _deliver(host, {"type": "request_file", "name": {"path": "a.txt"}})
    assert _sent(host) == []


def test_an_unusable_filename_is_reported_rather_than_raised(host):
    _deliver(host, {"type": "request_file", "name": "co:n<>|.txt"})
    [response] = _sent(host)
    assert response["type"] == "request_file_response"
    assert response["ok"] is False


# --- deleting a file ----------------------------------------------------------

def test_deleting_an_inbox_file_removes_it(host):
    target = _inbox(host) / "a.txt"
    target.write_bytes(b"1")
    _deliver(host, {"type": "delete_inbox_file", "name": "a.txt"})
    assert not target.exists()
    assert _sent(host) == [{"type": "delete_inbox_response", "name": "a.txt",
                            "ok": True}]


def test_deleting_a_missing_file_is_answered_with_the_reason(host):
    _deliver(host, {"type": "delete_inbox_file", "name": "gone.txt"})
    [response] = _sent(host)
    assert response["ok"] is False
    assert response["error"]


def test_deleting_without_permission_is_refused_with_a_reason(host):
    target = _inbox(host) / "a.txt"
    target.write_bytes(b"1")
    host.set_read_only(True)
    _deliver(host, {"type": "delete_inbox_file", "name": "a.txt"})
    assert target.exists()
    assert _sent(host)[-1]["error"] == "files not permitted"


def test_a_delete_with_a_non_string_name_is_ignored(host):
    _deliver(host, {"type": "delete_inbox_file", "name": 7})
    assert _sent(host) == []


def test_deleting_a_path_cannot_escape_the_inbox(host, tmp_path):
    outside = tmp_path / "secret.txt"
    outside.write_bytes(b"private")
    _deliver(host, {"type": "delete_inbox_file", "name": "../secret.txt"})
    assert outside.exists(), "the delete stayed inside the inbox"
    assert _sent(host)[-1]["ok"] is False


# --- permissions and outbound sends -------------------------------------------

def test_changing_permissions_tells_the_viewer(host):
    host.set_permissions(SessionPermissions.view_only())
    assert _sent(host)[-1] == {
        "type": "permissions",
        "value": SessionPermissions.view_only().to_dict(),
    }


def test_read_only_is_derived_from_the_input_flag(host):
    host.set_permissions(SessionPermissions.view_only())
    assert host.read_only is True
    host.set_permissions(SessionPermissions.full_control())
    assert host.read_only is False


def test_sending_before_the_channel_exists_is_a_no_op(bridge):
    host = WebRTCDesktopHost(token="secret")
    host._send_ctrl({"type": "permissions"})
    assert bridge.deferred == []


def test_a_channel_that_fails_mid_send_does_not_raise(host):
    host._control_channel.send_error = OSError("channel closed")
    host.set_permissions(SessionPermissions.view_only())


def test_a_channel_closed_between_queue_and_send_is_a_no_op(host):
    # `_send_ctrl` hops onto the asyncio loop, so the channel can go away
    # between the two halves; `_safe_channel_send` re-checks for exactly that.
    host._control_channel = None
    host._safe_channel_send("{}")
