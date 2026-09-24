"""The AT-SPI wire itself: what the backend actually sends down the bus.

`test_accessibility_linux.py` replaces `_AtspiConnection` with a fake tree,
which is the right shape for testing the *walk* -- and it leaves the whole
D-Bus call layer beneath it unexecuted. That is where the protocol lives, and
the protocol is where the surprises are:

* **The accessibility bus is not the session bus.** Its address comes from
  `org.a11y.Bus.GetAddress` on the session bus, and everything after that
  happens on a second connection to the address that call returns. Talking
  AT-SPI to the session bus reaches nobody.
* **An accessible is a *pair*.** The bus name of the owning application plus
  an object path inside it -- so references are `(sender, path)` tuples all
  the way down, and a call addressed with only a path goes to the wrong
  process.
* **The state bitfield arrives as two 32-bit words.** AT-SPI does not send
  one 64-bit value, so reading only the first word silently drops every
  state above bit 31 -- including SELECTED, which this backend reports.
* **Not implementing an interface is not an error.** A plain text node has no
  Component and therefore no rectangle; a walk that treated that as a failure
  would fail more often than it succeeded.

`SessionBus` is replaced rather than `_AtspiConnection`: the whole point is
to run the code that builds those calls. What it is replaced by is a
recorder, so each test can state the exact `(destination, path, interface,
member, signature, body)` that went out.

The bus is also where this backend gets its blast radius: `_is_available()`
opens a connection at import-decision time on every Linux desktop, so its
failure paths matter as much as its success one.
"""
from __future__ import annotations

import pytest

from je_auto_control.utils.accessibility.backends import linux_backend as atspi
from je_auto_control.utils.accessibility.backends.linux_backend import (
    _AtspiConnection, LinuxAccessibilityBackend,
)
from je_auto_control.utils.dbus_client import DBusError, Variant

ROOT = ("org.a11y.atspi.Registry", "/org/a11y/atspi/accessible/root")
APP = ("app.bus.name", "/org/a11y/atspi/accessible/1")
BUTTON = ("app.bus.name", "/org/a11y/atspi/accessible/2")


class _Bus:
    """A session bus that answers scripted replies and records the calls."""

    instances = []

    def __init__(self, address=None) -> None:
        self.address = address
        self.calls = []
        self.connected = False
        self.closed = False
        self.replies = {}
        self.errors = {}
        self.connect_error = None
        _Bus.instances.append(self)

    # -- the SessionBus surface --
    def connect(self):
        if self.connect_error is not None:
            raise self.connect_error
        self.connected = True

    def close(self):
        self.closed = True

    def __enter__(self):
        self.connect()
        return self

    def __exit__(self, *_exception):
        self.close()

    def call(self, destination, path, interface, member, signature, body,
             timeout=25.0):
        self.calls.append((destination, path, interface, member, signature,
                           list(body), timeout))
        key = (path, interface, member)
        if key in self.errors:
            raise self.errors[key]
        if (interface, member) in self.errors:
            raise self.errors[(interface, member)]
        if key in self.replies:
            return self.replies[key]
        return self.replies.get((interface, member), [])


@pytest.fixture
def bus(monkeypatch):
    """One bus for both connections, so a test can script either."""
    _Bus.instances = []
    instance = _Bus()
    instance.replies[("org.a11y.Bus", "GetAddress")] = ["unix:path=/a11y"]
    monkeypatch.setattr(atspi, "SessionBus", lambda address=None: instance)
    yield instance
    _Bus.instances = []


@pytest.fixture
def connection(bus):
    with _AtspiConnection() as opened:
        yield opened


def _call(bus, index=-1):
    """One recorded call, without the timeout."""
    return bus.calls[index][:6]


# --- finding the accessibility bus --------------------------------------------

def test_the_address_is_asked_of_the_session_bus(bus):
    with _AtspiConnection():
        pass
    destination, path, interface, member, signature, body = _call(bus, 0)
    assert (destination, path) == ("org.a11y.Bus", "/org/a11y/bus")
    assert (interface, member) == ("org.a11y.Bus", "GetAddress")
    assert (signature, body) == ("", [])


def test_the_connection_opens_on_the_address_it_was_given(monkeypatch):
    # A second connection, to a second bus. Reusing the session bus would
    # send AT-SPI calls somewhere that does not speak it.
    opened = []

    def _factory(address=None):
        instance = _Bus(address)
        instance.replies[("org.a11y.Bus", "GetAddress")] = ["unix:path=/a11y"]
        opened.append(instance)
        return instance

    monkeypatch.setattr(atspi, "SessionBus", _factory)
    with _AtspiConnection():
        pass
    assert [b.address for b in opened] == [None, "unix:path=/a11y"]


def test_the_connection_is_closed_on_the_way_out(bus):
    with _AtspiConnection():
        pass
    assert bus.closed is True


@pytest.mark.parametrize("reply", [[], [42], None])
def test_an_address_that_is_not_a_string_is_an_error(bus, reply):
    bus.replies[("org.a11y.Bus", "GetAddress")] = reply
    with pytest.raises(DBusError, match="GetAddress"):
        with _AtspiConnection():
            pass


def test_using_the_connection_unopened_says_which_mistake_it_was(bus):
    # The class is a context manager on purpose; forgetting the `with` is a
    # programming error worth naming rather than an AttributeError.
    with pytest.raises(DBusError, match="context manager"):
        _AtspiConnection().children(ROOT)


def test_the_root_is_the_registry(connection):
    assert connection.root == ROOT


# --- reads --------------------------------------------------------------------

def test_children_are_read_as_sender_and_path_pairs(connection, bus):
    bus.replies[("org.a11y.atspi.Accessible", "GetChildren")] = [
        [["app.bus.name", "/org/a11y/atspi/accessible/1"],
         ["app.bus.name", "/org/a11y/atspi/accessible/2"]],
    ]
    assert connection.children(ROOT) == [APP, BUTTON]


def test_a_child_entry_that_is_not_a_pair_is_dropped(connection, bus):
    # A malformed reply is a bug in the application, not a reason to fail the
    # whole walk of everything else on the desktop.
    bus.replies[("org.a11y.atspi.Accessible", "GetChildren")] = [
        ["not a pair", ["app.bus.name", "/1"], ["only-one"]],
    ]
    assert connection.children(ROOT) == [("app.bus.name", "/1")]


def test_an_empty_reply_reads_as_no_children(connection, bus):
    assert connection.children(ROOT) == []


def test_a_call_is_addressed_to_the_owning_application(connection, bus):
    connection.children(BUTTON)
    destination, path, interface, member, _signature, _body = _call(bus)
    assert destination == "app.bus.name", "the sender half of the reference"
    assert path == "/org/a11y/atspi/accessible/2"
    assert (interface, member) == ("org.a11y.atspi.Accessible", "GetChildren")


def test_a_property_is_unwrapped_from_its_variant(connection, bus):
    bus.replies[("org.freedesktop.DBus.Properties", "Get")] = [
        Variant("s", "OK"),
    ]
    assert connection.property(BUTTON, "Name") == "OK"
    _d, _p, interface, member, signature, body = _call(bus)
    assert (interface, member) == ("org.freedesktop.DBus.Properties", "Get")
    assert (signature, body) == ("ss", ["org.a11y.atspi.Accessible", "Name"])


def test_a_property_that_is_not_a_variant_is_passed_through(connection, bus):
    bus.replies[("org.freedesktop.DBus.Properties", "Get")] = ["plain"]
    assert connection.property(BUTTON, "Name") == "plain"


def test_a_property_with_no_reply_reads_as_none(connection, bus):
    assert connection.property(BUTTON, "Name") is None


def test_a_property_can_be_asked_of_another_interface(connection, bus):
    bus.replies[("org.freedesktop.DBus.Properties", "Get")] = [Variant("d", 5)]
    connection.property(BUTTON, "CurrentValue", "org.a11y.atspi.Value")
    _d, _p, _i, _m, _signature, body = _call(bus)
    assert body == ["org.a11y.atspi.Value", "CurrentValue"]


def test_the_role_name_is_read_as_text(connection, bus):
    bus.replies[("org.a11y.atspi.Accessible", "GetRoleName")] = ["push button"]
    assert connection.role_name(BUTTON) == "push button"


def test_a_missing_role_name_reads_as_empty(connection, bus):
    assert connection.role_name(BUTTON) == ""


def test_the_state_is_assembled_from_both_words(connection, bus):
    # AT-SPI sends the bitfield as two 32-bit words. Reading only the first
    # would drop every state above bit 31 -- SELECTED among them.
    bus.replies[("org.a11y.atspi.Accessible", "GetState")] = [[0, 1 << 25]]
    assert connection.state(BUTTON) == 1 << (32 + 25)


def test_the_low_word_lands_where_the_backend_looks_for_enabled(connection,
                                                                bus):
    bus.replies[("org.a11y.atspi.Accessible", "GetState")] = [[1 << 8, 0]]
    assert connection.state(BUTTON) & (1 << 8)


def test_extra_words_beyond_the_first_two_are_ignored(connection, bus):
    bus.replies[("org.a11y.atspi.Accessible", "GetState")] = [[0, 0, 0xFF]]
    assert connection.state(BUTTON) == 0


@pytest.mark.parametrize("reply", [[], [[]], [None]])
def test_a_state_reply_with_nothing_in_it_reads_as_zero(connection, bus,
                                                        reply):
    bus.replies[("org.a11y.atspi.Accessible", "GetState")] = reply
    assert connection.state(BUTTON) == 0


def test_extents_are_asked_in_screen_coordinates(connection, bus):
    # Screen is the only coordinate space whose numbers mean anything to a
    # caller that is about to click them.
    bus.replies[("org.a11y.atspi.Component", "GetExtents")] = [[1, 2, 3, 4]]
    assert connection.extents(BUTTON) == (1, 2, 3, 4)
    _d, _p, _i, _m, signature, body = _call(bus)
    assert (signature, body) == ("u", [0])


def test_an_accessible_with_no_component_interface_has_no_rectangle(
        connection, bus):
    # A plain text node implements no Component; that is not an error.
    bus.errors[("org.a11y.atspi.Component", "GetExtents")] = DBusError("no")
    assert connection.extents(BUTTON) == (0, 0, 0, 0)


@pytest.mark.parametrize("reply", [[], [[1, 2]]])
def test_a_short_extents_reply_reads_as_the_origin(connection, bus, reply):
    bus.replies[("org.a11y.atspi.Component", "GetExtents")] = reply
    assert connection.extents(BUTTON) == (0, 0, 0, 0)


def test_text_is_read_over_the_whole_range(connection, bus):
    bus.replies[("org.a11y.atspi.Text", "GetText")] = ["hello"]
    assert connection.text(BUTTON) == "hello"
    _d, _p, _i, _m, signature, body = _call(bus)
    assert (signature, body) == ("ii", [0, -1]), "0 to -1 is 'all of it'"


def test_an_accessible_with_no_text_interface_has_no_text(connection, bus):
    bus.errors[("org.a11y.atspi.Text", "GetText")] = DBusError("no Text")
    assert connection.text(BUTTON) is None


def test_an_empty_text_reply_reads_as_none(connection, bus):
    assert connection.text(BUTTON) is None


def test_a_numeric_value_is_read_from_the_value_interface(connection, bus):
    bus.replies[("org.freedesktop.DBus.Properties", "Get")] = [
        Variant("d", 0.75),
    ]
    assert connection.number(BUTTON) == 0.75


@pytest.mark.parametrize("reply,error", [
    ([Variant("s", "not a number")], None),
    ([None], None),
    (None, DBusError("no Value interface")),
])
def test_a_control_with_no_number_reads_as_none(connection, bus, reply, error):
    if error is not None:
        bus.errors[("org.freedesktop.DBus.Properties", "Get")] = error
    else:
        bus.replies[("org.freedesktop.DBus.Properties", "Get")] = reply
    assert connection.number(BUTTON) is None


# --- writes -------------------------------------------------------------------

def test_an_action_is_performed_by_index(connection, bus):
    bus.replies[("org.a11y.atspi.Action", "DoAction")] = [True]
    assert connection.do_action(BUTTON, 0) is True
    _d, _p, interface, member, signature, body = _call(bus)
    assert (interface, member) == ("org.a11y.atspi.Action", "DoAction")
    assert (signature, body) == ("i", [0])


def test_an_action_the_control_refuses_reports_failure(connection, bus):
    bus.replies[("org.a11y.atspi.Action", "DoAction")] = [False]
    assert connection.do_action(BUTTON) is False


def test_an_action_with_no_reply_reports_failure(connection, bus):
    assert connection.do_action(BUTTON) is False


def test_text_is_written_through_the_editable_interface(connection, bus):
    bus.replies[("org.a11y.atspi.EditableText", "SetTextContents")] = [True]
    assert connection.set_text(BUTTON, "typed") is True
    _d, _p, interface, member, signature, body = _call(bus)
    assert (interface, member) == ("org.a11y.atspi.EditableText",
                                   "SetTextContents")
    assert (signature, body) == ("s", ["typed"])


def test_a_write_the_control_refuses_reports_failure(connection, bus):
    bus.replies[("org.a11y.atspi.EditableText", "SetTextContents")] = [False]
    assert connection.set_text(BUTTON, "typed") is False


def test_focus_is_grabbed_through_the_component_interface(connection, bus):
    bus.replies[("org.a11y.atspi.Component", "GrabFocus")] = [True]
    assert connection.grab_focus(BUTTON) is True
    _d, _p, interface, member, _s, _b = _call(bus)
    assert (interface, member) == ("org.a11y.atspi.Component", "GrabFocus")


def test_a_focus_grab_the_control_refuses_reports_failure(connection, bus):
    assert connection.grab_focus(BUTTON) is False


# --- availability -------------------------------------------------------------

def test_availability_is_decided_by_reaching_the_root(monkeypatch, bus):
    monkeypatch.setattr(atspi.os, "name", "posix")
    bus.replies[("org.a11y.atspi.Accessible", "GetChildren")] = [[]]
    assert atspi._is_available() is True


def test_a_desktop_with_no_accessibility_bus_is_unavailable(monkeypatch, bus):
    monkeypatch.setattr(atspi.os, "name", "posix")
    bus.connect_error = DBusError("connection refused")
    assert atspi._is_available() is False


def test_a_bus_that_cannot_be_reached_at_all_is_unavailable(monkeypatch, bus):
    monkeypatch.setattr(atspi.os, "name", "posix")
    bus.connect_error = OSError("no such file or directory")
    assert atspi._is_available() is False


def test_off_posix_no_bus_is_even_attempted(monkeypatch, bus):
    monkeypatch.setattr(atspi.os, "name", "nt")
    assert atspi._is_available() is False
    assert bus.calls == [], "not one D-Bus round trip on Windows"


def test_the_backend_takes_its_availability_from_the_probe(monkeypatch):
    monkeypatch.setattr(atspi, "_is_available", lambda: True)
    assert LinuxAccessibilityBackend().available is True
    monkeypatch.setattr(atspi, "_is_available", lambda: False)
    assert LinuxAccessibilityBackend().available is False
