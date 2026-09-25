"""Linux accessibility backend, over AT-SPI2.

Linux had no accessibility backend at all: :func:`_build_backend` fell through
to the null one, while ``docs/CAPABILITY_MATRIX.md`` claimed "backend tests"
for Linux X11. This is the backend that makes the claim true.

AT-SPI2 is a D-Bus protocol, not a library, which is what makes it reachable
here without adding a dependency. The usual bindings (``pyatspi``,
``gi.repository.Atspi``) are distribution packages built against the system
GObject introspection data: they cannot be installed into a virtual
environment, so a project that depends on them is a project most users cannot
run. :mod:`je_auto_control.utils.dbus_client`, written for the XDG portal
handshake, already speaks enough D-Bus for this.

The shape of the protocol:

* The accessibility bus is *not* the session bus. Its address comes from
  ``org.a11y.Bus.GetAddress`` on the session bus, and everything else happens
  on a second connection to that address.
* An accessible object is addressed by a **pair** — the bus name of the
  application that owns it and an object path inside it — so references are
  ``(sender, path)`` tuples throughout rather than single strings.
* The root's children are applications; theirs are windows; theirs are the
  controls. Walking is therefore per-application, which is also what makes
  ``app_name`` cheap to honour.

Every read is defensive. An accessible can disappear between the call that
lists it and the call that describes it — the application closed a dialog, or
exited — and a walk that raised on that would fail more often than it
succeeded.
"""
import os
from typing import Any, Dict, List, Optional, Tuple

from je_auto_control.utils.accessibility.backends.base import AccessibilityBackend
from je_auto_control.utils.accessibility.element import (
    AccessibilityElement, AccessibilityNotAvailableError, element_matches,
)
from je_auto_control.utils.dbus_client import DBusError, SessionBus, Variant
from je_auto_control.utils.logging.logging_instance import autocontrol_logger

#: Where the session bus publishes the accessibility bus's address.
_BUS_NAME = "org.a11y.Bus"
#: Nodes a control search visits at most: the Windows backend's scan limits,
#: for a search of every window and for one named window.
_SEARCH_BUDGET = 1500
_SEARCH_SCOPED_BUDGET = 20000
_BUS_PATH = "/org/a11y/bus"

#: The registry that owns the tree's root.
_REGISTRY = "org.a11y.atspi.Registry"
_ROOT_PATH = "/org/a11y/atspi/accessible/root"

#: AT-SPI2 interfaces, as they appear on the wire.
_ACCESSIBLE = "org.a11y.atspi.Accessible"
_ACTION = "org.a11y.atspi.Action"
_COMPONENT = "org.a11y.atspi.Component"
_EDITABLE = "org.a11y.atspi.EditableText"
_TEXT = "org.a11y.atspi.Text"
_VALUE = "org.a11y.atspi.Value"
_PROPERTIES = "org.freedesktop.DBus.Properties"

#: ``GetExtents`` coordinate spaces. 0 is the screen, which is the only one
#: whose numbers mean anything to a caller about to click them.
_COORDS_SCREEN = 0

#: Bit positions in the ``GetState`` bitfield that this backend reads.
_STATE_ACTIVE = 1
_STATE_ENABLED = 8
_STATE_FOCUSED = 12
_STATE_SELECTED = 25

#: How many accessibles one focus search may examine. The search only enters
#: active windows, but a window can still hold a table with thousands of rows,
#: and "which one is focused?" must not turn into a walk of all of them.
_FOCUS_SCAN_LIMIT = 5000

#: A reference to one accessible: the owning application's bus name and the
#: object path inside it.
Reference = Tuple[str, str]


def _is_available() -> bool:
    """Whether an accessibility bus can be reached at all."""
    if os.name != "posix":
        return False
    try:
        with _AtspiConnection() as connection:
            connection.children(connection.root)
        return True
    except (DBusError, OSError) as error:
        autocontrol_logger.info("AT-SPI unavailable: %r", error)
        return False


class _AtspiConnection:
    """One connection to the accessibility bus, for the length of one call."""

    def __init__(self) -> None:
        self._bus: Optional[SessionBus] = None

    def __enter__(self) -> "_AtspiConnection":
        self._bus = SessionBus(address=self._address())
        self._bus.connect()
        return self

    def __exit__(self, *_exception: Any) -> None:
        if self._bus is not None:
            self._bus.close()
            self._bus = None

    @staticmethod
    def _address() -> str:
        """Ask the session bus where the accessibility bus is."""
        with SessionBus() as session:
            reply = session.call(_BUS_NAME, _BUS_PATH, _BUS_NAME,
                                 "GetAddress", "", [])
        if not reply or not isinstance(reply[0], str):
            raise DBusError("org.a11y.Bus.GetAddress returned no address")
        return reply[0]

    @property
    def root(self) -> Reference:
        return (_REGISTRY, _ROOT_PATH)

    def _require_bus(self) -> SessionBus:
        """Return the live bus, or say which mistake was made."""
        bus = self._bus
        if bus is None:
            raise DBusError(
                "AT-SPI connection is not open; use it as a context manager",
            )
        return bus

    def _call(self, reference: Reference, interface: str, member: str,
              signature: str = "", body: Optional[List[Any]] = None,
              timeout: float = 10.0) -> List[Any]:
        sender, path = reference
        return self._require_bus().call(
            sender, path, interface, member,
            signature, body or [], timeout=timeout,
        )

    # --- reads -------------------------------------------------------------

    def children(self, reference: Reference) -> List[Reference]:
        """The accessible's children, as ``(sender, path)`` pairs."""
        reply = self._call(reference, _ACCESSIBLE, "GetChildren")
        if not reply:
            return []
        return [(str(item[0]), str(item[1])) for item in reply[0]
                if isinstance(item, (list, tuple)) and len(item) >= 2]

    def property(self, reference: Reference, name: str,
                 interface: str = _ACCESSIBLE) -> Any:
        """One D-Bus property, unwrapped from its variant."""
        reply = self._call(reference, _PROPERTIES, "Get", "ss",
                           [interface, name])
        value = reply[0] if reply else None
        return value.value if isinstance(value, Variant) else value

    def role_name(self, reference: Reference) -> str:
        reply = self._call(reference, _ACCESSIBLE, "GetRoleName")
        return str(reply[0]) if reply else ""

    def state(self, reference: Reference) -> int:
        """The state bitfield, as one integer.

        AT-SPI sends it as two 32-bit words rather than one 64-bit value, so
        reading only the first would silently drop every state above bit 31.
        """
        reply = self._call(reference, _ACCESSIBLE, "GetState")
        words = list(reply[0]) if reply and reply[0] else []
        bits = 0
        for index, word in enumerate(words[:2]):
            bits |= int(word) << (32 * index)
        return bits

    def extents(self, reference: Reference) -> Tuple[int, int, int, int]:
        """``(left, top, width, height)`` in screen pixels, or zeroes."""
        try:
            reply = self._call(reference, _COMPONENT, "GetExtents", "u",
                               [_COORDS_SCREEN])
        except DBusError:
            # Not every accessible implements Component — a plain text node
            # has no rectangle, and that is not an error.
            return (0, 0, 0, 0)
        if not reply or len(reply[0]) < 4:
            return (0, 0, 0, 0)
        return tuple(int(value) for value in reply[0][:4])  # type: ignore[return-value]

    # --- writes ------------------------------------------------------------

    def do_action(self, reference: Reference, index: int = 0) -> bool:
        reply = self._call(reference, _ACTION, "DoAction", "i", [int(index)])
        return bool(reply and reply[0])

    def set_text(self, reference: Reference, value: str) -> bool:
        reply = self._call(reference, _EDITABLE, "SetTextContents", "s",
                           [str(value)])
        return bool(reply and reply[0])

    def text(self, reference: Reference) -> Optional[str]:
        try:
            reply = self._call(reference, _TEXT, "GetText", "ii", [0, -1])
        except DBusError:
            return None
        return str(reply[0]) if reply else None

    def number(self, reference: Reference) -> Optional[float]:
        try:
            return float(self.property(reference, "CurrentValue", _VALUE))
        except (DBusError, TypeError, ValueError):
            return None

    def grab_focus(self, reference: Reference) -> bool:
        reply = self._call(reference, _COMPONENT, "GrabFocus")
        return bool(reply and reply[0])


class LinuxAccessibilityBackend(AccessibilityBackend):
    """The AT-SPI2 tree, walked over D-Bus."""

    name = "linux-atspi"

    def __init__(self) -> None:
        self.available = _is_available()

    def _require(self) -> None:
        if not self.available:
            raise AccessibilityNotAvailableError(
                "no AT-SPI accessibility bus. Install and start at-spi2-core, "
                "and make sure the toolkit's accessibility bridge is enabled "
                "(GTK_MODULES=gail:atk-bridge, QT_ACCESSIBILITY=1).",
            )

    def list_elements(self, app_name: Optional[str] = None,
                      max_results: int = 200,
                      window_title: Optional[str] = None,
                      ) -> List[AccessibilityElement]:
        self._require()
        results: List[AccessibilityElement] = []
        with _AtspiConnection() as connection:
            for application in connection.children(connection.root):
                if len(results) >= max_results:
                    break
                name = _safe_name(connection, application)
                if app_name is not None and name != app_name:
                    continue
                self._walk(connection, application, name, results,
                           max_results, window_title)
        return results[:max_results]

    def _walk(self, connection: _AtspiConnection, reference: Reference,
              app_name: str, results: List[AccessibilityElement],
              max_results: int, window_title: Optional[str],
              depth: int = 0) -> None:
        """Depth-first, and bounded: a broken tree must not hang the caller."""
        if len(results) >= max_results or depth > 32:
            return
        try:
            children = connection.children(reference)
        except DBusError:
            return
        for child in children:
            if len(results) >= max_results:
                return
            converted = _convert(connection, child, app_name)
            if converted is None:
                continue
            # Scoping to a window is not just filtering: below a window the
            # tree is orders of magnitude smaller, so this both narrows the
            # answer and shortens the walk.
            if depth == 0 and window_title is not None:
                if window_title.lower() not in converted.name.lower():
                    continue
            results.append(converted)
            self._walk(connection, child, app_name, results, max_results,
                       window_title, depth + 1)

    # --- control patterns --------------------------------------------------

    def _find(self, connection: _AtspiConnection, name: Optional[str],
              role: Optional[str], app_name: Optional[str],
              window_title: Optional[str] = None,
              contains: bool = False) -> Optional[Reference]:
        """The reference behind the first element that matches."""
        # One budget for the whole search, as the Windows backend's scan limits.
        budget = [_SEARCH_SCOPED_BUDGET if window_title else _SEARCH_BUDGET]
        for application in connection.children(connection.root):
            owner = _safe_name(connection, application)
            if app_name is not None and owner != app_name:
                continue
            found = self._search(connection, application, owner, name, role,
                                 contains, window_title=window_title, budget=budget)
            if found is not None:
                return found
        return None

    def _search(self, connection: _AtspiConnection, reference: Reference,
                app_name: str, name: Optional[str], role: Optional[str],
                contains: bool, depth: int = 0,
                window_title: Optional[str] = None,
                budget: Optional[List[int]] = None) -> Optional[Reference]:
        """Depth-first search for a match, within ``budget`` nodes in all.

        Bounded by depth only, a window holding a 20,000-cell table made
        100,000 bus calls (each with a 10 s timeout) to report "not found";
        the Windows backend stops at the same limits.
        """
        budget = [_SEARCH_BUDGET] if budget is None else budget
        if depth > 32 or budget[0] <= 0:
            return None
        try:
            children = connection.children(reference)
        except DBusError:
            return None
        for child in children:
            found = self._search_child(connection, child, app_name,
                                       (name, role, contains), depth, window_title, budget)
            if found is not None or budget[0] < 0:
                return found
        return None

    def _search_child(self, connection: _AtspiConnection, child: Reference,
                      app_name: str, query: Tuple[Optional[str], Optional[str], bool],
                      depth: int, window_title: Optional[str],
                      budget: List[int]) -> Optional[Reference]:
        """``child`` if it matches ``(name, role, contains)``, else the first match below it."""
        budget[0] -= 1
        if budget[0] < 0:
            return None
        name, role, contains = query
        converted = _convert(connection, child, app_name)
        # The same window scoping _walk applies: window_title was dropped
        # here, so get_value('Name', window_title='Firefox') read the first
        # 'Name' of whichever app came first.
        if depth == 0 and _outside_window(converted, window_title):
            return None
        if converted is not None and element_matches(converted, name, role, app_name, contains):
            return child
        return self._search(connection, child, app_name, name, role, contains,
                            depth + 1, budget=budget)

    def get_value(self, name: Optional[str] = None, role: Optional[str] = None,
                  app_name: Optional[str] = None,
                  automation_id: Optional[str] = None,
                  window_title: Optional[str] = None,
                  contains: bool = False) -> Optional[str]:
        self._require()
        del automation_id  # AT-SPI has no equivalent of a UIA automation id
        with _AtspiConnection() as connection:
            reference = self._find(connection, name, role, app_name,
                                   window_title, contains)
            if reference is None:
                return None
            text = connection.text(reference)
            if text is not None:
                return text
            number = connection.number(reference)
            return None if number is None else str(number)

    def set_value(self, value: str, name: Optional[str] = None,
                  role: Optional[str] = None, app_name: Optional[str] = None,
                  automation_id: Optional[str] = None) -> bool:
        self._require()
        del automation_id
        with _AtspiConnection() as connection:
            reference = self._find(connection, name, role, app_name)
            if reference is None:
                return False
            try:
                return connection.set_text(reference, value)
            except DBusError as error:
                autocontrol_logger.info("set_value failed: %r", error)
                return False

    def invoke(self, name: Optional[str] = None, role: Optional[str] = None,
               app_name: Optional[str] = None,
               automation_id: Optional[str] = None) -> bool:
        self._require()
        del automation_id
        with _AtspiConnection() as connection:
            reference = self._find(connection, name, role, app_name)
            if reference is None:
                return False
            try:
                return connection.do_action(reference, 0)
            except DBusError as error:
                autocontrol_logger.info("invoke failed: %r", error)
                return False

    def set_focus(self, name: Optional[str] = None, role: Optional[str] = None,
                  app_name: Optional[str] = None,
                  automation_id: Optional[str] = None) -> bool:
        self._require()
        del automation_id
        with _AtspiConnection() as connection:
            reference = self._find(connection, name, role, app_name)
            if reference is None:
                return False
            try:
                return connection.grab_focus(reference)
            except DBusError as error:
                autocontrol_logger.info("set_focus failed: %r", error)
                return False

    def focused_element(self) -> Optional[AccessibilityElement]:
        """The accessible holding focus, searched inside active windows only.

        AT-SPI has no "what is focused?" call on the bus, so this looks for
        ``STATE_FOCUSED`` -- but only below top-level windows that are
        ``STATE_ACTIVE``, which is where keyboard focus lives.
        """
        self._require()
        with _AtspiConnection() as connection:
            for application in connection.children(connection.root):
                owner = _safe_name(connection, application)
                for window in _children_or_none(connection, application):
                    if not _has_state(connection, window, _STATE_ACTIVE):
                        continue
                    found = _focused_below(connection, window, owner)
                    if found is not None:
                        return found
        return None

    def get_state(self, name: Optional[str] = None,
                  role: Optional[str] = None, app_name: Optional[str] = None,
                  automation_id: Optional[str] = None,
                  window_title: Optional[str] = None,
                  contains: bool = False) -> Optional[Dict[str, Any]]:
        self._require()
        del automation_id
        with _AtspiConnection() as connection:
            reference = self._find(connection, name, role, app_name,
                                   window_title, contains)
            if reference is None:
                return None
            bits = connection.state(reference)
            state: Dict[str, Any] = {
                "enabled": bool(bits & (1 << _STATE_ENABLED)),
                "focused": bool(bits & (1 << _STATE_FOCUSED)),
                "selected": bool(bits & (1 << _STATE_SELECTED)),
            }
            # A key is absent when the control does not have the concept,
            # which is a different answer from the value being empty.
            text = connection.text(reference)
            if text is not None:
                state["value"] = text
            number = connection.number(reference)
            if number is not None:
                state["number"] = number
            return state


def _safe_name(connection: _AtspiConnection, reference: Reference) -> str:
    try:
        return str(connection.property(reference, "Name") or "")
    except DBusError:
        return ""


def _convert(connection: _AtspiConnection, reference: Reference,
             app_name: str) -> Optional[AccessibilityElement]:
    """One accessible as an :class:`AccessibilityElement`, or None."""
    try:
        name = _safe_name(connection, reference)
        role = connection.role_name(reference)
        bounds = connection.extents(reference)
        bits = connection.state(reference)
    except DBusError:
        # The accessible went away between being listed and being described.
        return None
    if not name and not role:
        return None
    return AccessibilityElement(
        name=name, role=role, bounds=bounds, app_name=app_name,
        native_id=reference[1],
        enabled=bool(bits & (1 << _STATE_ENABLED)),
    )


def _children_or_none(connection: _AtspiConnection,
                      reference: Reference) -> List[Reference]:
    """Children of ``reference``; none when it went away while being asked."""
    try:
        return connection.children(reference)
    except DBusError:
        return []


def _has_state(connection: _AtspiConnection, reference: Reference,
               bit: int) -> bool:
    try:
        return bool(connection.state(reference) & (1 << bit))
    except DBusError:
        return False


def _focused_below(connection: _AtspiConnection, window: Reference,
                   app_name: str,
                   limit: int = _FOCUS_SCAN_LIMIT) -> Optional[AccessibilityElement]:
    """Depth-first search of one window for the focused accessible, bounded."""
    stack = [window]
    while stack and limit > 0:
        limit -= 1
        reference = stack.pop()
        if _has_state(connection, reference, _STATE_FOCUSED):
            return _convert(connection, reference, app_name)
        stack.extend(reversed(_children_or_none(connection, reference)))
    return None


def _outside_window(window: Optional[AccessibilityElement],
                    window_title: Optional[str]) -> bool:
    """Whether a top-level ``window`` falls outside the requested title."""
    if window_title is None:
        return False
    return window is None or window_title.lower() not in window.name.lower()
