"""The capture tiers below the three compositor CLI helpers.

No compositor helper is guaranteed to be installed — GNOME has not shipped
``gnome-screenshot`` by default since 42 — so the capture layer falls back to
``xdg-desktop-portal`` and, above everything, honours an operator-supplied
command. These tests drive both without a Wayland session: the session bus
connection is a fake that answers from a script, and the operator command is
any program that writes a file.

The input side of the portal lives in ``test_wayland_oeffis.py``; it needs a
file descriptor rather than a file, so it cannot share this route.
"""
import subprocess
from unittest.mock import patch

import pytest

from je_auto_control.linux_wayland import capture as wayland_capture
from je_auto_control.linux_wayland import portal as wayland_portal
from je_auto_control.linux_wayland import screen as wayland_screen
from je_auto_control.utils.exception.exceptions import AutoControlScreenException


def _png(size=(2, 2), rgb=(9, 9, 9)) -> bytes:
    from io import BytesIO

    from PIL import Image
    buffer = BytesIO()
    Image.new("RGB", size, rgb).save(buffer, format="PNG")
    return buffer.getvalue()


def _no_binaries(name):
    return None


# === Operator override =====================================================

def test_override_command_wins_over_every_installed_tool(monkeypatch):
    """An operator who names a command means it — detection does not get a
    vote, or the override could not rescue a box where grim exists but is
    broken."""
    monkeypatch.setenv(wayland_capture.CAPTURE_COMMAND_ENV,
                       "/usr/bin/mycap --png {output}")
    png = _png()
    captured = []

    def run(argv, **_kwargs):
        captured.append(list(argv))
        with open(argv[-1], "wb") as handle:
            handle.write(png)
        return subprocess.CompletedProcess(argv, 0, b"", b"")  # nosemgrep

    with patch.object(wayland_capture, "binary_path",
                      return_value="/usr/bin/grim"), \
         patch.object(wayland_capture.subprocess, "run", side_effect=run):
        image = wayland_screen.grab_image()

    assert image.size == (2, 2)
    assert captured[0][:2] == ["/usr/bin/mycap", "--png"]
    assert captured[0][2].endswith(".png")


def test_override_keeps_a_spaced_path_as_one_argument(monkeypatch):
    """The path is substituted per-token after shlex.split, never
    concatenated into a command line, so a temp dir with a space in it
    cannot split into two arguments (or be quoted into a shell)."""
    monkeypatch.setenv(wayland_capture.CAPTURE_COMMAND_ENV, "cap {output}")
    argv = wayland_capture._override_argv("/tmp/a b/shot.png")
    assert argv == ["cap", "/tmp/a b/shot.png"]


def test_override_without_the_output_placeholder_is_rejected(monkeypatch):
    """A command with nowhere to write would silently produce an empty file;
    say so at the boundary instead."""
    monkeypatch.setenv(wayland_capture.CAPTURE_COMMAND_ENV, "grim -")
    with pytest.raises(AutoControlScreenException, match=r"\{output\}"):
        wayland_capture._override_argv("/tmp/x.png")


def test_override_is_reported_as_the_active_tool(monkeypatch):
    monkeypatch.setenv(wayland_capture.CAPTURE_COMMAND_ENV, "cap {output}")
    assert wayland_capture.available_tool() == "$" + \
        wayland_capture.CAPTURE_COMMAND_ENV


def test_blank_override_is_ignored(monkeypatch):
    monkeypatch.setenv(wayland_capture.CAPTURE_COMMAND_ENV, "   ")
    with patch.object(wayland_capture, "binary_path", side_effect=_no_binaries), \
         patch.object(wayland_portal, "is_available", return_value=False):
        assert wayland_capture.available_tool() is None


# === Portal tier ===========================================================

def test_portal_runs_only_after_every_cli_helper_is_absent(monkeypatch):
    monkeypatch.delenv(wayland_capture.CAPTURE_COMMAND_ENV, raising=False)
    png = _png()
    with patch.object(wayland_capture, "binary_path",
                      return_value="/usr/bin/grim"), \
         patch.object(wayland_portal, "capture_png",
                      return_value=png) as portal_call, \
         patch.object(wayland_capture.subprocess, "run",
                      return_value=subprocess.CompletedProcess(  # nosemgrep
                          ["grim"], 0, png, b"")):
        wayland_capture.grab_png()
    portal_call.assert_not_called()


def test_portal_is_used_when_no_helper_is_installed(monkeypatch):
    monkeypatch.delenv(wayland_capture.CAPTURE_COMMAND_ENV, raising=False)
    png = _png()
    with patch.object(wayland_capture, "binary_path", side_effect=_no_binaries), \
         patch.object(wayland_portal, "is_available", return_value=True), \
         patch.object(wayland_portal, "capture_png", return_value=png):
        result = wayland_capture.grab_png([0, 0, 1, 1])
    assert result.data == png
    # The portal always captures everything, so the region must be cropped.
    assert result.region_applied is False


def test_portal_is_reported_as_the_active_tool(monkeypatch):
    monkeypatch.delenv(wayland_capture.CAPTURE_COMMAND_ENV, raising=False)
    with patch.object(wayland_capture, "binary_path", side_effect=_no_binaries), \
         patch.object(wayland_portal, "is_available", return_value=True):
        assert wayland_capture.available_tool() == "xdg-desktop-portal"


# === Portal response handling ==============================================
#
# The portal answers with a signal directed at the connection that called, so
# these drive the module the way the bus does: a fake connection that records
# the order things happened in. The real bus, the real marshalling and a real
# portal are exercised in ``docker/portal_verify.py`` — a mock cannot show
# that a directed signal never reaches a second connection, which is the
# defect this design replaced.

_URI = "file:///run/user/1000/doc/ab/screenshot.png"


class _FakeBus:
    """A session bus that answers from a script and records the order."""

    sender_token = "1_9"

    def __init__(self, body=None, handle=None, error=None):
        self.body = [0, {"uri": _URI}] if body is None else body
        self.handle = handle
        self.error = error
        self.events = []
        self.rules = []
        self.awaited_paths = None

    def __enter__(self):
        return self

    def __exit__(self, *_exception):
        self.events.append("close")

    def add_match(self, rule):
        self.events.append("add_match")
        self.rules.append(rule)

    def call(self, _destination, _path, _interface, member, _signature,
             _body, timeout=None):
        del timeout
        self.events.append(f"call:{member}")
        return [self.handle] if self.handle else []

    def wait_for_signal(self, paths, _interface, _member, _timeout):
        self.events.append("wait")
        self.awaited_paths = list(paths)
        if self.error is not None:
            raise self.error
        return self.body


def _with_bus(bus):
    """Patch the module's connection factory to hand back ``bus``."""
    return patch.object(wayland_portal._dbus_client, "SessionBus",
                        return_value=bus)


def test_portal_extracts_the_uri_from_a_response_signal():
    assert wayland_portal._uri_from_response([0, {"uri": _URI}]) == _URI


def test_portal_rejects_a_response_body_it_cannot_read():
    """A Response that is not ``(u, a{sv})`` must be named, not indexed into."""
    with pytest.raises(AutoControlScreenException, match="cannot read"):
        wayland_portal._uri_from_response([0])


def test_portal_reports_a_user_cancelled_request():
    """Response code 1 is the user dismissing the dialog; that has to read as
    a cancellation, not as a parse failure."""
    with pytest.raises(AutoControlScreenException, match="dismissed"):
        wayland_portal._uri_from_response([1, {}])


def test_portal_rejects_a_success_with_no_uri():
    with pytest.raises(AutoControlScreenException, match="no image URI"):
        wayland_portal._uri_from_response([0, {}])


def test_portal_decodes_a_percent_escaped_file_uri():
    assert wayland_portal._path_from_uri(
        "file:///run/user/1000/my%20shot.png",
    ) == "/run/user/1000/my shot.png"


def test_portal_rejects_a_non_file_uri():
    with pytest.raises(AutoControlScreenException, match="non-file URI"):
        wayland_portal._path_from_uri("https://example.invalid/x.png")


def test_portal_reads_then_deletes_the_file_it_was_handed(tmp_path):
    """The portal hands over a real file; leaving one behind per capture
    would fill the runtime dir over a long automation run."""
    target = tmp_path / "shot.png"
    target.write_bytes(_png())
    assert wayland_portal._read_and_discard(str(target)) == _png()
    assert not target.exists()


def test_portal_is_unavailable_without_a_session_bus(monkeypatch):
    """No bus address is the one case where this tier cannot even be tried."""
    monkeypatch.delenv("DBUS_SESSION_BUS_ADDRESS", raising=False)
    assert wayland_portal.is_available() is False
    with pytest.raises(AutoControlScreenException, match="session bus"):
        wayland_portal.capture_png(timeout=0.1)


def test_portal_subscribes_before_it_calls():
    """The ordering the whole design turns on.

    The portal emits ``Response`` as soon as it has an answer, and it emits it
    to the caller. Calling first and subscribing afterwards is a race that
    loses the answer whenever the portal is quick — which, with no consent
    dialog to show, it always is.
    """
    bus = _FakeBus()
    with _with_bus(bus), patch.object(wayland_portal, "_path_from_uri",
                                      return_value=""), \
            patch.object(wayland_portal, "_read_and_discard",
                         return_value=_png()):
        wayland_portal.capture_png(timeout=1.0)
    assert bus.events[:3] == ["add_match", "call:Screenshot", "wait"]


def test_portal_subscribes_to_the_path_it_predicted():
    """The request path is built from our own unique name and handle token."""
    bus = _FakeBus()
    with _with_bus(bus), patch.object(wayland_portal, "_path_from_uri",
                                      return_value=""), \
            patch.object(wayland_portal, "_read_and_discard",
                         return_value=_png()):
        wayland_portal.capture_png(timeout=1.0)
    assert len(bus.awaited_paths) == 1
    predicted = bus.awaited_paths[0]
    assert predicted.startswith(
        "/org/freedesktop/portal/desktop/request/1_9/je_auto_control_")
    assert predicted in bus.rules[0]
    assert "member='Response'" in bus.rules[0]


def test_portal_also_follows_a_handle_that_differs_from_the_prediction():
    """A portal that ignores ``handle_token`` answers somewhere of its own.

    The specification tells clients to follow the returned handle, so both
    paths have to be live: the predicted one could not be dropped (the answer
    may already be on its way) and the returned one could not be subscribed
    to any earlier than this.
    """
    elsewhere = "/org/freedesktop/portal/desktop/request/1_9/portal_chose"
    bus = _FakeBus(handle=elsewhere)
    with _with_bus(bus), patch.object(wayland_portal, "_path_from_uri",
                                      return_value=""), \
            patch.object(wayland_portal, "_read_and_discard",
                         return_value=_png()):
        wayland_portal.capture_png(timeout=1.0)
    assert bus.events[:4] == ["add_match", "call:Screenshot", "add_match",
                              "wait"]
    assert elsewhere in bus.awaited_paths
    assert len(bus.awaited_paths) == 2


def test_portal_gives_each_request_its_own_token():
    """Two captures sharing a token would put both answers on one path."""
    first = wayland_portal._handle_token()
    second = wayland_portal._handle_token()
    assert first != second
    for token in (first, second):
        assert token.replace("_", "").isalnum(), \
            "the token becomes an object-path element, so it must be [A-Za-z0-9_]"


def test_portal_times_out_rather_than_waiting_forever():
    """A consent dialog nobody answers must not hang the caller's script."""
    bus = _FakeBus(error=wayland_portal._dbus_client.DBusError("no answer"))
    with _with_bus(bus):
        with pytest.raises(AutoControlScreenException, match="did not answer"):
            wayland_portal.capture_png(timeout=0.05)
    assert bus.events[-1] == "close", "the connection must not be left open"


def test_portal_reports_a_bus_that_went_away():
    """The bus dropping mid-request is a capture failure, not a crash."""
    bus = _FakeBus()
    error = wayland_portal._dbus_client.DBusError("the session bus closed")
    with _with_bus(bus), patch.object(bus, "call", side_effect=error):
        with pytest.raises(AutoControlScreenException,
                           match="could not be reached"):
            wayland_portal.capture_png(timeout=1.0)


def test_portal_captures_end_to_end_from_a_response_signal(tmp_path):
    """The whole tier wired together: signal -> URI -> bytes -> cleanup.

    Only the URI-to-path step is stubbed, because a portal URI is an absolute
    POSIX path that a Windows dev host cannot represent; that step has its own
    tests above.
    """
    target = tmp_path / "portal-shot.png"
    target.write_bytes(_png())
    bus = _FakeBus(body=[0, {"uri": _URI}])
    seen = []

    def resolve(value):
        seen.append(value)
        return str(target)

    with _with_bus(bus), patch.object(wayland_portal, "_path_from_uri",
                                      side_effect=resolve):
        data = wayland_portal.capture_png(timeout=5.0)

    assert seen == [_URI]
    assert data == _png()
    assert not target.exists()
