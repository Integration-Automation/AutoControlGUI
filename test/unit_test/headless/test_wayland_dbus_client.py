"""The hand-written D-Bus marshalling behind the xdg-desktop-portal tier.

``je_auto_control.linux_wayland._dbus_client`` exists because a portal answers
with a signal *directed at the connection that asked*, so the subscription and
the call have to share one connection — which rules out shelling out to
``gdbus`` and leaves marshalling D-Bus by hand.

Hand-written marshalling is exactly the kind of code that passes review and
fails on a real bus, so it is checked twice. Absolute correctness — that these
bytes are the bytes a real ``dbus-daemon`` accepts and that a real portal
answers — is settled in ``docker/portal_verify.py`` against a real bus. What
is checked here is everything a bus is not needed for: the alignment rules,
the signature walker, container types, address parsing, and that a message
this module writes is one it reads back unchanged.

No session bus is touched: the socket is a loopback object that hands back
whatever was written to it.
"""
import struct

import pytest

from je_auto_control.linux_wayland import _dbus_client
from je_auto_control.linux_wayland._dbus_client import (
    DBusError, SessionBus, Variant, _Reader, _SignatureReader, _Writer,
)


class _LoopbackSocket:
    """Whatever is written can be read back, so a message can round-trip."""

    def __init__(self):
        self.written = b""
        self.readable = b""
        self.closed = False

    def sendall(self, data):
        self.written += data

    def settimeout(self, _timeout):
        return None

    def recv(self, size):
        chunk, self.readable = self.readable[:size], self.readable[size:]
        return chunk

    def close(self):
        self.closed = True


def _bus():
    """A connection whose socket is loopback, so nothing leaves the process."""
    bus = SessionBus(address="unix:path=/nonexistent")
    bus._socket = _LoopbackSocket()
    bus.unique_name = ":1.9"
    return bus


# === Signatures ============================================================

@pytest.mark.parametrize("signature, expected", [
    ("s", ["s"]),
    ("sa{sv}", ["s", "a{sv}"]),
    ("ua{sv}", ["u", "a{sv}"]),
    ("a(yv)", ["a(yv)"]),
    ("aas", ["aas"]),
    ("(us)o", ["(us)", "o"]),
    ("a{sa{sv}}", ["a{sa{sv}}"]),
])
def test_signature_walker_takes_one_whole_type_at_a_time(signature, expected):
    """A container has to be followed to its close, however deeply it nests."""
    reader = _SignatureReader(signature)
    taken = []
    while not reader.done():
        taken.append(reader.take_complete())
    assert taken == expected


# === Byte-exact marshalling ================================================

def test_a_string_is_length_then_bytes_then_a_nul():
    writer = _Writer()
    writer.value("s", "abc")
    assert writer.data == struct.pack("<I", 3) + b"abc\x00"


def test_a_signature_is_a_single_length_byte_not_a_uint32():
    """``g`` is the one string-ish type with a one-byte length."""
    writer = _Writer()
    writer.value("g", "a{sv}")
    assert writer.data == b"\x05a{sv}\x00"


def test_a_uint32_is_padded_to_its_own_alignment():
    """A byte followed by a uint32 leaves three bytes of padding, not zero."""
    writer = _Writer()
    writer.value("y", 1)
    writer.value("u", 2)
    assert writer.data == b"\x01" + b"\x00" * 3 + struct.pack("<I", 2)


def test_an_empty_array_is_a_zero_length_and_nothing_else():
    writer = _Writer()
    writer.value("as", [])
    assert writer.data == struct.pack("<I", 0)


def test_a_boolean_is_a_uint32_not_a_byte():
    writer = _Writer()
    writer.value("b", True)
    assert writer.data == struct.pack("<I", 1)


# === Round trips ===========================================================

@pytest.mark.parametrize("signature, value", [
    ("s", "hello"),
    ("s", ""),
    ("o", "/org/freedesktop/portal/desktop"),
    ("u", 4294967295),
    ("b", False),
    ("y", 200),
    ("as", ["one", "two", "three"]),
    ("as", []),
    ("a{sv}", {}),
    ("(us)", (7, "seven")),
])
def test_values_survive_a_write_and_a_read(signature, value):
    writer = _Writer()
    writer.value(signature, value)
    assert _Reader(writer.data).value(signature) == value


def test_a_variant_map_survives_with_its_types_intact():
    """``a{sv}`` is what every portal option map is, so it is the one to get
    right: a boolean stays a boolean and a string stays a string."""
    options = {"interactive": Variant("b", False),
               "handle_token": Variant("s", "je_auto_control_1")}
    writer = _Writer()
    writer.value("a{sv}", options)
    assert _Reader(writer.data).value("a{sv}") == {
        "interactive": False, "handle_token": "je_auto_control_1"}


def test_an_array_of_structs_survives_the_alignment_it_forces():
    """``a(yv)`` is the message header's own type: structs align to eight,
    which is padding the length prefix must not count."""
    fields = [(1, Variant("o", "/a")), (3, Variant("s", "Screenshot"))]
    writer = _Writer()
    writer.value("a(yv)", fields)
    assert _Reader(writer.data).value("a(yv)") == [
        (1, "/a"), (3, "Screenshot")]


def test_a_signature_that_wants_more_members_than_it_was_given_is_rejected():
    with pytest.raises(DBusError):
        _Writer().value("(us)", (7,))


def test_a_type_this_does_not_marshal_says_so():
    with pytest.raises(DBusError, match="cannot marshal"):
        _Writer().value("d", 1.5)


# === Whole messages ========================================================

def test_a_message_this_writes_is_one_it_reads_back():
    """Header fields, body and the padding between them, end to end."""
    bus = _bus()
    bus.send(_dbus_client.SIGNAL, {
        _dbus_client.FIELD_PATH: ("o", "/org/freedesktop/portal/desktop"),
        _dbus_client.FIELD_INTERFACE: ("s", "org.freedesktop.portal.Request"),
        _dbus_client.FIELD_MEMBER: ("s", "Response"),
        _dbus_client.FIELD_SIGNATURE: ("g", "ua{sv}"),
    }, "ua{sv}", [0, {"uri": Variant("s", "file:///tmp/shot.png")}])

    bus._socket.readable = bus._socket.written
    message = bus.read_message(deadline=_never())
    assert message.type == _dbus_client.SIGNAL
    assert message.path == "/org/freedesktop/portal/desktop"
    assert message.interface == "org.freedesktop.portal.Request"
    assert message.member == "Response"
    assert message.body == [0, {"uri": "file:///tmp/shot.png"}]


def test_a_message_with_no_body_reads_back_as_no_body():
    """``Hello`` is sent with an empty signature and must not decode one."""
    bus = _bus()
    bus.send(_dbus_client.METHOD_CALL, {
        _dbus_client.FIELD_PATH: ("o", _dbus_client.BUS_PATH),
        _dbus_client.FIELD_MEMBER: ("s", "Hello"),
    }, "", [])
    bus._socket.readable = bus._socket.written
    message = bus.read_message(deadline=_never())
    assert message.member == "Hello"
    assert message.body == []


def test_two_messages_in_one_read_are_not_run_together():
    """A bus writes when it likes, so two messages can arrive in one chunk."""
    bus = _bus()
    for member in ("First", "Second"):
        bus.send(_dbus_client.SIGNAL, {
            _dbus_client.FIELD_PATH: ("o", "/x"),
            _dbus_client.FIELD_MEMBER: ("s", member),
            _dbus_client.FIELD_SIGNATURE: ("g", "s"),
        }, "s", [member.lower()])
    bus._socket.readable = bus._socket.written
    assert bus.read_message(deadline=_never()).member == "First"
    assert bus.read_message(deadline=_never()).member == "Second"


def test_serials_rise_so_a_reply_can_be_matched_to_its_call():
    bus = _bus()
    fields = {_dbus_client.FIELD_MEMBER: ("s", "Ping")}
    assert bus.send(_dbus_client.METHOD_CALL, fields, "", []) == 1
    assert bus.send(_dbus_client.METHOD_CALL, fields, "", []) == 2


def test_more_arguments_than_the_signature_declares_is_rejected():
    with pytest.raises(DBusError, match="more arguments"):
        _bus().send(_dbus_client.SIGNAL,
                    {_dbus_client.FIELD_MEMBER: ("s", "X")}, "s", ["a", "b"])


def test_fewer_arguments_than_the_signature_declares_is_rejected():
    with pytest.raises(DBusError, match="fewer arguments"):
        _bus().send(_dbus_client.SIGNAL,
                    {_dbus_client.FIELD_MEMBER: ("s", "X")}, "ss", ["a"])


def test_an_implausibly_large_message_is_refused_before_it_is_buffered():
    """The length is the bus's word for it, so it is bounded before use."""
    bus = _bus()
    bus._socket.readable = struct.pack(
        "<BBBBIII", ord("l"), _dbus_client.SIGNAL, 0, 1, 2 ** 31, 1, 0)
    with pytest.raises(DBusError, match="implausibly large"):
        bus.read_message(deadline=_never())


def test_a_big_endian_message_is_named_rather_than_misread():
    bus = _bus()
    bus._socket.readable = struct.pack(
        ">BBBBIII", ord("B"), _dbus_client.SIGNAL, 0, 1, 0, 1, 0)
    with pytest.raises(DBusError, match="big-endian"):
        bus.read_message(deadline=_never())


# === Addresses =============================================================

@pytest.mark.parametrize("address, expected", [
    ("unix:path=/run/user/1000/bus", ("/run/user/1000/bus", False)),
    ("unix:path=/tmp/dbus-x,guid=deadbeef", ("/tmp/dbus-x", False)),
    ("unix:abstract=/tmp/dbus-y,guid=f00", ("/tmp/dbus-y", True)),
    ("tcp:host=localhost,port=1;unix:path=/run/bus", ("/run/bus", False)),
])
def test_a_bus_address_resolves_to_a_socket(address, expected):
    assert _dbus_client._socket_target(address) == expected


def test_an_address_with_no_unix_transport_is_refused():
    with pytest.raises(DBusError, match="no usable unix transport"):
        _dbus_client._socket_target("tcp:host=localhost,port=1234")


def test_availability_follows_the_environment(monkeypatch):
    monkeypatch.delenv("DBUS_SESSION_BUS_ADDRESS", raising=False)
    assert _dbus_client.is_available() is False
    assert _dbus_client.session_address() is None
    monkeypatch.setenv("DBUS_SESSION_BUS_ADDRESS", "unix:path=/run/bus")
    assert _dbus_client.is_available() is True


def test_connecting_without_an_address_says_which_variable_is_missing(monkeypatch):
    monkeypatch.delenv("DBUS_SESSION_BUS_ADDRESS", raising=False)
    with pytest.raises(DBusError, match="DBUS_SESSION_BUS_ADDRESS"):
        SessionBus().connect()


def test_the_sender_token_is_the_unique_name_as_a_path_element():
    """The portal builds the request path out of this, so both sides have to
    mangle the name the same way or the client subscribes to the wrong path."""
    bus = SessionBus(address="unix:path=/x")
    bus.unique_name = ":1.42"
    assert bus.sender_token == "1_42"


def test_closing_twice_is_safe_and_closes_the_socket():
    bus = _bus()
    socket = bus._socket
    bus.close()
    bus.close()
    assert socket.closed


def test_a_dbus_error_is_part_of_the_framework_family():
    """Every containment boundary catches AutoControlException; a sibling of
    it would escape all of them."""
    from je_auto_control.utils.exception.exceptions import AutoControlException
    assert issubclass(DBusError, AutoControlException)


def _never() -> float:
    """A deadline far enough away that the loopback socket always wins."""
    import time
    return time.monotonic() + 60.0
