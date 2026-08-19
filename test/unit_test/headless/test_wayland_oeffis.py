"""The portal hop that hands libei an EIS file descriptor.

``ConnectToEIS`` returns a file descriptor over D-Bus, which no command-line
tool can pass into this process — so unlike the Screenshot portal there is no
``gdbus`` shortcut, and liboeffis does the session dance instead. These tests
drive its event loop against a fake library: the success path, the user
declining, the portal going away, and the timeout. All four have to end in a
released context, because a leaked oeffis handle keeps a remote-desktop grant
open on the user's session.
"""
from unittest.mock import patch

import pytest

from je_auto_control.linux_wayland import oeffis as oeffis_mod


HANDLE = 0x0EFF15


class FakeOeffis:
    """A liboeffis whose event stream the test scripts."""

    def __init__(self, events=(), eis_fd=11, error=b""):
        self.calls = []
        self._events = list(events)
        self._eis_fd = eis_fd
        self._error = error

    def oeffis_new(self, _user_data):
        self.calls.append(("new",))
        return HANDLE

    def oeffis_unref(self, handle):
        self.calls.append(("unref", handle))
        return None

    def oeffis_create_session(self, handle, devices):
        self.calls.append(("create_session", handle, devices))

    def oeffis_get_fd(self, _handle):
        return 0

    def oeffis_dispatch(self, _handle):
        self.calls.append(("dispatch",))

    def oeffis_get_event(self, _handle):
        return self._events.pop(0) if self._events else oeffis_mod.OEFFIS_EVENT_NONE

    def oeffis_get_eis_fd(self, _handle):
        return self._eis_fd

    def oeffis_get_error_message(self, _handle):
        return self._error


@pytest.fixture(autouse=True)
def _select_always_ready():
    """Report the oeffis fd readable; the fake's fd is not a real socket."""
    with patch.object(oeffis_mod.select, "select",
                      side_effect=lambda r, _w, _x, _t: (list(r), [], [])):
        yield


def test_connect_returns_the_eis_fd_and_a_live_session():
    fake = FakeOeffis(events=[oeffis_mod.OEFFIS_EVENT_CONNECTED_TO_EIS])
    eis_fd, session = oeffis_mod.connect_eis_fd(symbols=fake)
    assert eis_fd == 11
    # The session must NOT be released yet: dropping it ends the grant.
    assert ("unref", HANDLE) not in fake.calls
    session.close()
    assert ("unref", HANDLE) in fake.calls


def test_connect_requests_only_the_devices_this_backend_emits():
    """The consent dialog shows the user what is being granted, so asking for
    a touchscreen this backend never drives would widen the grant for no
    benefit."""
    fake = FakeOeffis(events=[oeffis_mod.OEFFIS_EVENT_CONNECTED_TO_EIS])
    oeffis_mod.connect_eis_fd(symbols=fake)
    created = next(c for c in fake.calls if c[0] == "create_session")
    assert created[2] == (oeffis_mod.OEFFIS_DEVICE_KEYBOARD
                          | oeffis_mod.OEFFIS_DEVICE_POINTER)
    assert not created[2] & oeffis_mod.OEFFIS_DEVICE_TOUCHSCREEN


def test_event_constants_match_liboeffis_h():
    """Checked against liboeffis.h (Debian 1.5.0-3 and upstream main, which
    agree). CLOSED precedes DISCONNECTED — the opposite of what the names
    suggest, and it was wrong here until the header was read.
    """
    assert oeffis_mod.OEFFIS_EVENT_NONE == 0
    assert oeffis_mod.OEFFIS_EVENT_CONNECTED_TO_EIS == 1
    assert oeffis_mod.OEFFIS_EVENT_CLOSED == 2
    assert oeffis_mod.OEFFIS_EVENT_DISCONNECTED == 3


def test_device_constants_match_liboeffis_h():
    assert oeffis_mod.OEFFIS_DEVICE_ALL_DEVICES == 0
    assert oeffis_mod.OEFFIS_DEVICE_KEYBOARD == 1
    assert oeffis_mod.OEFFIS_DEVICE_POINTER == 2
    assert oeffis_mod.OEFFIS_DEVICE_TOUCHSCREEN == 4


def test_a_closed_session_reads_as_the_user_declining():
    fake = FakeOeffis(events=[oeffis_mod.OEFFIS_EVENT_CLOSED],
                      error=b"permission denied")
    with pytest.raises(oeffis_mod.OeffisUnavailable, match="closed"):
        oeffis_mod.connect_eis_fd(symbols=fake)
    assert ("unref", HANDLE) in fake.calls


def test_the_librarys_own_error_text_reaches_the_message():
    fake = FakeOeffis(events=[oeffis_mod.OEFFIS_EVENT_CLOSED],
                      error=b"permission denied")
    with pytest.raises(oeffis_mod.OeffisUnavailable, match="permission denied"):
        oeffis_mod.connect_eis_fd(symbols=fake)


def test_a_disconnect_is_reported_and_the_handle_released():
    fake = FakeOeffis(events=[oeffis_mod.OEFFIS_EVENT_DISCONNECTED])
    with pytest.raises(oeffis_mod.OeffisUnavailable, match="disconnected"):
        oeffis_mod.connect_eis_fd(symbols=fake)
    assert ("unref", HANDLE) in fake.calls


def test_an_unanswered_consent_dialog_times_out():
    """Nobody clicking the dialog must not wedge the caller's script."""
    fake = FakeOeffis(events=[])
    with pytest.raises(oeffis_mod.OeffisUnavailable, match="did not answer"):
        oeffis_mod.connect_eis_fd(symbols=fake, timeout=0.05)
    assert ("unref", HANDLE) in fake.calls


def test_a_success_without_an_fd_is_still_a_failure():
    fake = FakeOeffis(events=[oeffis_mod.OEFFIS_EVENT_CONNECTED_TO_EIS],
                      eis_fd=-1)
    with pytest.raises(oeffis_mod.OeffisUnavailable, match="no EIS fd"):
        oeffis_mod.connect_eis_fd(symbols=fake)
    assert ("unref", HANDLE) in fake.calls


def test_a_null_context_is_reported():
    class _NoContext(FakeOeffis):
        def oeffis_new(self, _user_data):
            return 0

    symbols = _NoContext()
    with pytest.raises(oeffis_mod.OeffisUnavailable, match="NULL"):
        oeffis_mod.connect_eis_fd(symbols=symbols)


def test_missing_library_reads_as_unavailable():
    with patch.object(oeffis_mod, "load_symbols", return_value=None):
        assert oeffis_mod.is_available() is False
        with pytest.raises(oeffis_mod.OeffisUnavailable, match="not found"):
            oeffis_mod.connect_eis_fd()


def test_closing_a_session_twice_is_harmless():
    fake = FakeOeffis(events=[oeffis_mod.OEFFIS_EVENT_CONNECTED_TO_EIS])
    _, session = oeffis_mod.connect_eis_fd(symbols=fake)
    session.close()
    session.close()
    assert [c for c in fake.calls if c[0] == "unref"] == [("unref", HANDLE)]
