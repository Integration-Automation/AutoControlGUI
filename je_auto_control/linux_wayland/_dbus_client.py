"""A minimal D-Bus session-bus client, in the standard library alone.

This exists because of one property of the XDG portal protocol: a portal call
returns only a *request handle*, and the answer arrives later as a ``Response``
signal — **directed at the unique bus name that made the call**. The bus routes
a directed message to its destination and nowhere else, so a listener on a
second connection never receives it, whatever match rules it adds.

That rules out the obvious shell-out. ``gdbus call`` and ``gdbus monitor`` are
two processes with two unique names, so the monitor is not the caller and the
Response is not addressed to it; measured against a real ``dbus-daemon``, it
sees the call go past and the answer never arrive. The only listener that
does see it is a full bus monitor (``dbus-monitor``, which asks the bus for
``BecomeMonitor``), and making a screenshot require permission to observe every
message on the user's session bus is a poor trade for a fallback tier.

So the subscription and the call happen on one connection here, which is what
every portal client library does and what the protocol is designed for. The
cost is marshalling D-Bus by hand; the scope is kept to exactly what a portal
conversation needs — connect, authenticate, ``Hello``, ``AddMatch``, one method
call, and read signals until the matching one arrives. It is deliberately not a
general D-Bus binding: no properties, no introspection, no object export, no
file-descriptor passing (:mod:`je_auto_control.linux_wayland.oeffis` uses
liboeffis for the one call that needs that).

Every failure is an :class:`AutoControlException` subclass, so the containment
boundaries that catch the family keep working.
"""
from __future__ import annotations

import contextlib
import os
import socket
import struct
import time
from typing import Any, Dict, List, Optional, Tuple

from je_auto_control.utils.exception.exceptions import AutoControlException


#: Message types, from the D-Bus specification.
METHOD_CALL = 1
METHOD_RETURN = 2
ERROR = 3
SIGNAL = 4

#: Header field codes.
FIELD_PATH = 1
FIELD_INTERFACE = 2
FIELD_MEMBER = 3
FIELD_ERROR_NAME = 4
FIELD_REPLY_SERIAL = 5
FIELD_DESTINATION = 6
FIELD_SENDER = 7
FIELD_SIGNATURE = 8

#: ``NO_REPLY_EXPECTED``. Declared for completeness; nothing here uses it,
#: because every call this makes is one whose answer is worth waiting for.
FLAG_NO_REPLY_EXPECTED = 1

BUS_NAME = "org.freedesktop.DBus"
BUS_PATH = "/org/freedesktop/DBus"
BUS_INTERFACE = "org.freedesktop.DBus"

_ADDRESS_ENV = "DBUS_SESSION_BUS_ADDRESS"
_MAX_MESSAGE = 128 * 1024 * 1024  # the specification's own ceiling
_ALIGNMENT = {"y": 1, "b": 4, "n": 2, "q": 2, "i": 4, "u": 4,
              "x": 8, "t": 8, "d": 8, "s": 4, "o": 4, "g": 1,
              "a": 4, "(": 8, "{": 8, "v": 1, "h": 4}


class DBusError(AutoControlException):
    """The session bus is unreachable, or answered with an error."""


class Variant:
    """A value with an explicit D-Bus type, for the ``a{sv}`` option maps."""

    __slots__ = ("signature", "value")

    def __init__(self, signature: str, value: Any) -> None:
        self.signature = signature
        self.value = value

    def __repr__(self) -> str:
        return f"Variant({self.signature!r}, {self.value!r})"


# --- marshalling ----------------------------------------------------------


class _Writer:
    """Little-endian marshaller. Alignment is relative to the message start."""

    def __init__(self, offset: int = 0) -> None:
        self._parts: List[bytes] = []
        self._length = offset

    def align(self, boundary: int) -> None:
        padding = (-self._length) % boundary
        if padding:
            self._parts.append(bytes(padding))
            self._length += padding

    def raw(self, data: bytes) -> None:
        self._parts.append(data)
        self._length += len(data)

    def byte(self, value: int) -> None:
        self.raw(struct.pack("<B", value & 0xFF))

    def uint32(self, value: int) -> None:
        self.align(4)
        self.raw(struct.pack("<I", value & 0xFFFFFFFF))

    def string(self, value: str) -> None:
        encoded = value.encode("utf-8")
        self.uint32(len(encoded))
        self.raw(encoded + b"\x00")

    def signature(self, value: str) -> None:
        encoded = value.encode("ascii")
        self.byte(len(encoded))
        self.raw(encoded + b"\x00")

    def value(self, sig: str, value: Any) -> None:
        """Write one complete value of the given single signature."""
        _write_value(self, _SignatureReader(sig), value)

    @property
    def data(self) -> bytes:
        return b"".join(self._parts)

    def __len__(self) -> int:
        return self._length


class _SignatureReader:
    """Walks a signature string one complete type at a time."""

    def __init__(self, text: str) -> None:
        self.text = text
        self.index = 0

    def done(self) -> bool:
        return self.index >= len(self.text)

    def peek(self) -> str:
        return self.text[self.index]

    def take(self) -> str:
        code = self.text[self.index]
        self.index += 1
        return code

    def take_complete(self) -> str:
        """Take one whole type, following containers to their close."""
        start = self.index
        code = self.take()
        if code == "a":
            self.take_complete()
        elif code in "({":
            closing = ")" if code == "(" else "}"
            while self.peek() != closing:
                self.take_complete()
            self.take()
        return self.text[start:self.index]


def _write_value(writer: _Writer, reader: _SignatureReader, value: Any) -> None:
    code = reader.take()
    if code == "y":
        writer.byte(int(value))
    elif code == "b":
        writer.uint32(1 if value else 0)
    elif code == "u":
        writer.uint32(int(value))
    elif code in "so":
        writer.string(str(value))
    elif code == "g":
        writer.signature(str(value))
    elif code == "v":
        _write_variant(writer, value)
    elif code == "a":
        _write_array(writer, reader, value)
    elif code in "({":
        _write_struct(writer, reader, code, value)
    else:
        raise DBusError(f"cannot marshal D-Bus type {code!r}")


def _write_variant(writer: _Writer, value: Any) -> None:
    variant = value if isinstance(value, Variant) else _guess_variant(value)
    writer.signature(variant.signature)
    writer.value(variant.signature, variant.value)


def _guess_variant(value: Any) -> Variant:
    if isinstance(value, bool):
        return Variant("b", value)
    if isinstance(value, int):
        return Variant("u", value)
    if isinstance(value, str):
        return Variant("s", value)
    raise DBusError(f"no obvious D-Bus type for {type(value).__name__}")


def _write_array(writer: _Writer, reader: _SignatureReader, value: Any) -> None:
    element = reader.take_complete()
    writer.align(4)
    # The length prefix counts the elements only, and it is written before
    # the padding that aligns the first one — so the body is built separately
    # at the offset it will actually occupy.
    body_start = len(writer) + 4
    padding = (-body_start) % _ALIGNMENT.get(element[0], 1)
    body = _Writer(body_start + padding)
    items = value.items() if isinstance(value, dict) else value
    for item in items:
        body.align(_ALIGNMENT.get(element[0], 1))
        _write_value(body, _SignatureReader(element), item)
    writer.uint32(len(body) - body_start - padding)
    writer.raw(bytes(padding))
    writer.raw(body.data)


def _write_struct(writer: _Writer, reader: _SignatureReader, code: str,
                  value: Any) -> None:
    closing = ")" if code == "(" else "}"
    writer.align(8)
    for item in value:
        if reader.peek() == closing:
            raise DBusError("too many members for this struct signature")
        _write_value(writer, reader, item)
    if reader.peek() != closing:
        raise DBusError("too few members for this struct signature")
    reader.take()


class _Reader:
    """Little-endian demarshaller over one complete message."""

    def __init__(self, data: bytes, offset: int = 0) -> None:
        self.data = data
        self.offset = offset

    def align(self, boundary: int) -> None:
        self.offset += (-self.offset) % boundary

    def take(self, count: int) -> bytes:
        if self.offset + count > len(self.data):
            raise DBusError("truncated D-Bus message")
        chunk = self.data[self.offset:self.offset + count]
        self.offset += count
        return chunk

    def byte(self) -> int:
        return self.take(1)[0]

    def uint32(self) -> int:
        self.align(4)
        return struct.unpack("<I", self.take(4))[0]

    def string(self) -> str:
        length = self.uint32()
        text = self.take(length).decode("utf-8", errors="replace")
        self.take(1)
        return text

    def signature(self) -> str:
        length = self.byte()
        text = self.take(length).decode("ascii", errors="replace")
        self.take(1)
        return text

    def value(self, sig: str) -> Any:
        return _read_value(self, _SignatureReader(sig))


def _read_value(reader: _Reader, signature: _SignatureReader) -> Any:
    code = signature.take()
    if code == "y":
        return reader.byte()
    if code == "b":
        return bool(reader.uint32())
    if code == "u":
        return reader.uint32()
    if code in "so":
        return reader.string()
    if code == "g":
        return reader.signature()
    if code == "v":
        return reader.value(reader.signature())
    if code == "a":
        return _read_array(reader, signature)
    if code in "({":
        return _read_struct(reader, signature, code)
    raise DBusError(f"cannot demarshal D-Bus type {code!r}")


def _read_array(reader: _Reader, signature: _SignatureReader) -> Any:
    element = signature.take_complete()
    length = reader.uint32()
    reader.align(_ALIGNMENT.get(element[0], 1))
    end = reader.offset + length
    items = []
    while reader.offset < end:
        reader.align(_ALIGNMENT.get(element[0], 1))
        items.append(_read_value(reader, _SignatureReader(element)))
    if element.startswith("{"):
        return {key: value for key, value in items}
    return items


def _read_struct(reader: _Reader, signature: _SignatureReader,
                 code: str) -> tuple:
    closing = ")" if code == "(" else "}"
    reader.align(8)
    members = []
    while signature.peek() != closing:
        members.append(_read_value(reader, signature))
    signature.take()
    return tuple(members)


class Message:
    """One decoded D-Bus message: the header fields that matter, and the body."""

    __slots__ = ("type", "serial", "fields", "body")

    def __init__(self, message_type: int, serial: int,
                 fields: Dict[int, Any], body: List[Any]) -> None:
        self.type = message_type
        self.serial = serial
        self.fields = fields
        self.body = body

    @property
    def path(self) -> str:
        return self.fields.get(FIELD_PATH, "")

    @property
    def interface(self) -> str:
        return self.fields.get(FIELD_INTERFACE, "")

    @property
    def member(self) -> str:
        return self.fields.get(FIELD_MEMBER, "")

    @property
    def reply_serial(self) -> int:
        return self.fields.get(FIELD_REPLY_SERIAL, 0)

    @property
    def error_name(self) -> str:
        return self.fields.get(FIELD_ERROR_NAME, "")


# --- the connection -------------------------------------------------------


def session_address() -> Optional[str]:
    """The session bus address, or None when this process has no session bus."""
    address = os.environ.get(_ADDRESS_ENV, "").strip()
    return address or None


def is_available() -> bool:
    """Whether a session bus address is set, so connecting is worth trying."""
    return session_address() is not None


def _socket_target(address: str) -> Tuple[str, bool]:
    """Pick a connectable ``unix:`` transport out of a bus address.

    :return: the socket path and whether it is in the abstract namespace.
    """
    for candidate in address.split(";"):
        if not candidate.startswith("unix:"):
            continue
        options = dict(
            part.split("=", 1) for part in candidate[len("unix:"):].split(",")
            if "=" in part)
        if "path" in options:
            return options["path"], False
        if "abstract" in options:
            return options["abstract"], True
    raise DBusError(f"no usable unix transport in {address!r}")


class SessionBus:
    """An authenticated connection to the session bus, as a context manager."""

    def __init__(self, address: Optional[str] = None) -> None:
        self.address = address or session_address()
        self.unique_name = ""
        self._socket: Optional[socket.socket] = None
        self._serial = 0
        self._buffer = b""
        #: Messages read while waiting for a method reply. A portal's Response
        #: signal and its method return come from two different senders, so
        #: the bus gives no ordering between them and the signal can arrive
        #: first — dropping it here would be a wait that never ends.
        self._queued: List[Message] = []

    # --- lifecycle --------------------------------------------------------

    def __enter__(self) -> "SessionBus":
        self.connect()
        return self

    def __exit__(self, *_exception: Any) -> None:
        self.close()

    def connect(self) -> None:
        """Open the socket, authenticate, and say ``Hello``."""
        if self.address is None:
            raise DBusError(
                f"{_ADDRESS_ENV} is not set, so there is no session bus to "
                f"reach the desktop portal on",
            )
        path, abstract = _socket_target(self.address)
        try:
            self._socket = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
            self._socket.connect(("\0" + path) if abstract else path)
        except OSError as error:
            self.close()
            raise DBusError(f"cannot reach the session bus: {error}") from error
        self._authenticate()
        self.unique_name = self.call(
            BUS_NAME, BUS_PATH, BUS_INTERFACE, "Hello", "", [])[0]

    def close(self) -> None:
        """Drop the connection; never raise from teardown."""
        if self._socket is not None:
            with contextlib.suppress(OSError):
                self._socket.close()
            self._socket = None

    @property
    def sender_token(self) -> str:
        """This connection's name as the portal spells it inside object paths."""
        return self.unique_name.lstrip(":").replace(".", "_")

    # --- authentication ---------------------------------------------------

    def _authenticate(self) -> None:
        """The SASL EXTERNAL handshake, which is a uid in hex over a socket."""
        uid = str(os.getuid()).encode("ascii")
        self._send_raw(b"\x00AUTH EXTERNAL " + uid.hex().encode("ascii")
                       + b"\r\n")
        reply = self._read_line()
        if not reply.startswith("OK"):
            raise DBusError(f"the session bus refused authentication: {reply}")
        self._send_raw(b"BEGIN\r\n")

    def _send_raw(self, data: bytes) -> None:
        if self._socket is None:
            raise DBusError("the session bus connection is closed")
        try:
            self._socket.sendall(data)
        except OSError as error:
            raise DBusError(f"writing to the session bus failed: {error}") from error

    def _read_line(self, timeout: float = 10.0) -> str:
        """Read one CRLF-terminated line of the auth conversation."""
        deadline = time.monotonic() + timeout
        while b"\r\n" not in self._buffer:
            self._fill(deadline - time.monotonic())
        line, _, self._buffer = self._buffer.partition(b"\r\n")
        return line.decode("utf-8", errors="replace")

    # --- reading ----------------------------------------------------------

    def _fill(self, timeout: float) -> None:
        """Read whatever is available, or fail once the deadline has passed."""
        if self._socket is None:
            raise DBusError("the session bus connection is closed")
        if timeout <= 0:
            raise DBusError("the session bus did not answer in time")
        self._socket.settimeout(timeout)
        try:
            chunk = self._socket.recv(65536)
        except socket.timeout as error:
            raise DBusError("the session bus did not answer in time") from error
        except OSError as error:
            raise DBusError(f"reading from the session bus failed: {error}") from error
        if not chunk:
            raise DBusError("the session bus closed the connection")
        self._buffer += chunk

    def read_message(self, deadline: float) -> Message:
        """Read one whole message, or fail when the deadline passes."""
        while len(self._buffer) < 16:
            self._fill(deadline - time.monotonic())
        endian, message_type, _flags, _version = struct.unpack(
            "<BBBB", self._buffer[:4])
        if endian != ord("l"):
            raise DBusError("big-endian D-Bus messages are not supported")
        body_length, serial, fields_length = struct.unpack(
            "<III", self._buffer[4:16])
        header_end = 16 + fields_length
        total = header_end + ((-header_end) % 8) + body_length
        if total > _MAX_MESSAGE:
            raise DBusError("the session bus sent an implausibly large message")
        while len(self._buffer) < total:
            self._fill(deadline - time.monotonic())
        raw, self._buffer = self._buffer[:total], self._buffer[total:]
        return _decode(raw, message_type, serial, fields_length, header_end)

    # --- writing ----------------------------------------------------------

    def _next_serial(self) -> int:
        self._serial += 1
        return self._serial

    def send(self, message_type: int, fields: Dict[int, Tuple[str, Any]],
             signature: str, body: List[Any], flags: int = 0) -> int:
        """Marshal and send one message; return its serial."""
        payload = _Writer()
        for code, value in body_pairs(signature, body):
            payload.value(code, value)
        serial = self._next_serial()
        header = _Writer()
        header.raw(struct.pack("<BBBB", ord("l"), message_type, flags, 1))
        header.raw(struct.pack("<II", len(payload), serial))
        header.value("a(yv)", [
            (code, Variant(field_signature, value))
            for code, (field_signature, value) in sorted(fields.items())])
        header.align(8)
        self._send_raw(header.data + payload.data)
        return serial

    def call(self, destination: str, path: str, interface: str, member: str,
             signature: str, body: List[Any],
             timeout: float = 25.0) -> List[Any]:
        """Make a method call and return the reply body."""
        fields = {
            FIELD_PATH: ("o", path),
            FIELD_INTERFACE: ("s", interface),
            FIELD_MEMBER: ("s", member),
            FIELD_DESTINATION: ("s", destination),
        }
        if signature:
            fields[FIELD_SIGNATURE] = ("g", signature)
        serial = self.send(METHOD_CALL, fields, signature, body)
        deadline = time.monotonic() + timeout
        while True:
            message = self.read_message(deadline)
            if message.reply_serial != serial:
                self._queued.append(message)
                continue
            if message.type == ERROR:
                detail = message.body[0] if message.body else ""
                raise DBusError(f"{message.error_name}: {detail}".strip(": "))
            if message.type == METHOD_RETURN:
                return message.body

    def add_match(self, rule: str) -> None:
        """Subscribe to signals, and wait for the bus to confirm the rule.

        Waiting matters twice over: a malformed rule is reported rather than
        silently never matching, and the round trip proves the subscription is
        in place before the call that provokes the signal is made.
        """
        self.call(BUS_NAME, BUS_PATH, BUS_INTERFACE, "AddMatch", "s", [rule])

    def wait_for_signal(self, paths: List[str], interface: str, member: str,
                        timeout: float) -> List[Any]:
        """Read until the signal we subscribed to arrives, or time out."""
        def matches(message: Message) -> bool:
            return (message.type == SIGNAL and message.member == member
                    and message.interface == interface
                    and message.path in paths)

        for index, message in enumerate(self._queued):
            if matches(message):
                del self._queued[index]
                return message.body
        self._queued.clear()
        deadline = time.monotonic() + max(0.0, timeout)
        while True:
            message = self.read_message(deadline)
            if matches(message):
                return message.body


def body_pairs(signature: str, body: List[Any]):
    """Pair each top-level type in a signature with its argument."""
    reader = _SignatureReader(signature)
    for value in body:
        if reader.done():
            raise DBusError("more arguments than the signature declares")
        yield reader.take_complete(), value
    if not reader.done():
        raise DBusError("fewer arguments than the signature declares")


def _decode(raw: bytes, message_type: int, serial: int, fields_length: int,
            header_end: int) -> Message:
    """Turn one complete message's bytes into a :class:`Message`."""
    reader = _Reader(raw, 12)
    fields: Dict[int, Any] = {}
    reader.uint32()  # the header array's own length, already read
    end = 16 + fields_length
    while reader.offset < end:
        reader.align(8)
        code = reader.byte()
        fields[code] = reader.value(reader.signature())
    reader.offset = header_end + ((-header_end) % 8)
    body: List[Any] = []
    signature = fields.get(FIELD_SIGNATURE, "")
    if signature:
        walker = _SignatureReader(signature)
        while not walker.done():
            body.append(_read_value(reader, _SignatureReader(
                walker.take_complete())))
    return Message(message_type, serial, fields, body)


__all__ = [
    "BUS_INTERFACE", "BUS_NAME", "BUS_PATH", "DBusError", "ERROR",
    "METHOD_CALL", "METHOD_RETURN", "Message", "SIGNAL", "SessionBus",
    "Variant", "is_available", "session_address",
]
