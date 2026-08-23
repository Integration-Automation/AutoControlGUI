"""Headless tests for the Linux AT-SPI accessibility backend. No Qt, no bus.

The backend's real behaviour is checked against a live bus and a live GTK
application by ``docker/x11_atspi_verify.py`` — a mock cannot tell you whether
at-spi2 agrees with the bytes you send. What is worth pinning here is the
part that has nothing to do with the bus: how a reply is turned into an
:class:`AccessibilityElement`, how the walk is bounded, and what the backend
does when there is no bus at all, which is the case on every developer
machine that is not Linux.
"""
import sys

import pytest

from je_auto_control.utils.accessibility.element import (
    AccessibilityElement, AccessibilityNotAvailableError,
)
from je_auto_control.utils.dbus_client import DBusError


atspi = pytest.importorskip(
    "je_auto_control.utils.accessibility.backends.linux_backend",
    exc_type=ImportError)


class FakeConnection:
    """A tree of accessibles, answering the calls the backend makes."""

    def __init__(self, tree=None, names=None, roles=None, extents=None,
                 states=None):
        self.tree = tree or {}
        self.names = names or {}
        self.roles = roles or {}
        self.extents_map = extents or {}
        self.states = states or {}
        self.texts = {}
        self.numbers = {}
        self.errors = {}        # reference -> DBusError to raise on a write
        self.actions = []
        self.written = []
        self.focused = []
        self.write_result = True
        self.entered = 0
        self.exited = 0

    # context manager, so the backend's `with` blocks work unchanged
    def __enter__(self):
        self.entered += 1
        return self

    def __exit__(self, *_exception):
        self.exited += 1

    @property
    def root(self):
        return ("registry", "/root")

    def children(self, reference):
        return list(self.tree.get(reference, []))

    def property(self, reference, name, interface=None):
        del interface
        return self.names.get(reference, "") if name == "Name" else ""

    def role_name(self, reference):
        return self.roles.get(reference, "")

    def state(self, reference):
        return self.states.get(reference, 1 << 8)

    def extents(self, reference):
        return self.extents_map.get(reference, (0, 0, 0, 0))

    def text(self, reference):
        if reference in self.errors:
            raise self.errors[reference]
        return self.texts.get(reference)

    def number(self, reference):
        return self.numbers.get(reference)

    # --- writes, recorded rather than sent ---------------------------------

    def do_action(self, reference, index=0):
        if reference in self.errors:
            raise self.errors[reference]
        self.actions.append((reference, index))
        return self.write_result

    def set_text(self, reference, value):
        if reference in self.errors:
            raise self.errors[reference]
        self.written.append((reference, value))
        return self.write_result

    def grab_focus(self, reference):
        if reference in self.errors:
            raise self.errors[reference]
        self.focused.append(reference)
        return self.write_result


APP = ("app", "/app")
WINDOW = ("app", "/window")
BUTTON = ("app", "/button")


def _tree_connection():
    return FakeConnection(
        tree={("registry", "/root"): [APP], APP: [WINDOW], WINDOW: [BUTTON]},
        names={APP: "zenity", WINDOW: "autocontrol-dialog", BUTTON: "OK"},
        roles={WINDOW: "dialog", BUTTON: "push button"},
        extents={WINDOW: (-1280, 0, 310, 233), BUTTON: (-1200, 100, 60, 24)},
    )


@pytest.fixture()
def backend(monkeypatch):
    """An available backend whose bus is the fake tree above."""
    connection = _tree_connection()
    monkeypatch.setattr(atspi, "_AtspiConnection", lambda: connection)
    instance = atspi.LinuxAccessibilityBackend.__new__(
        atspi.LinuxAccessibilityBackend)
    instance.available = True
    instance.connection = connection
    return instance


# --- availability ----------------------------------------------------------


def test_unavailable_backend_says_what_to_install():
    """"No bus" and "no package" look the same from here, so name both."""
    instance = atspi.LinuxAccessibilityBackend.__new__(
        atspi.LinuxAccessibilityBackend)
    instance.available = False
    with pytest.raises(AccessibilityNotAvailableError) as caught:
        instance.list_elements()
    message = str(caught.value)
    assert "at-spi2-core" in message
    assert "atk-bridge" in message


@pytest.mark.skipif(sys.platform.startswith("linux"),
                    reason="on Linux the real probe decides")
def test_off_linux_the_backend_is_never_available():
    assert atspi._is_available() is False


# --- turning a reply into an element ---------------------------------------


def test_walk_collects_the_tree_below_each_application(backend):
    found = backend.list_elements()
    assert [element.name for element in found] == [
        "autocontrol-dialog", "OK"]
    assert all(isinstance(element, AccessibilityElement) for element in found)


def test_elements_carry_the_application_they_came_from(backend):
    """app_name is what a caller filters on, and the walk is per-application."""
    assert {element.app_name for element in backend.list_elements()} == {"zenity"}


def test_negative_extents_survive_as_negative(backend):
    """A monitor left of the primary one puts a window at a negative x.

    Reading the extents as unsigned would turn -1280 into 4293967296 and send
    every click derived from it to the wrong screen.
    """
    dialog = backend.list_elements()[0]
    assert dialog.bounds == (-1280, 0, 310, 233)
    assert dialog.center == (-1280 + 155, 116)


def test_app_name_filter_skips_other_applications(backend):
    assert backend.list_elements(app_name="zenity")
    assert backend.list_elements(app_name="something else") == []


def test_max_results_bounds_the_walk(backend):
    assert len(backend.list_elements(max_results=1)) == 1


def test_window_title_scopes_to_one_window(backend):
    """Below a window the tree is orders of magnitude smaller.

    So scoping both narrows the answer and shortens the walk, rather than
    filtering a full result set afterwards.
    """
    assert [element.name
            for element in backend.list_elements(window_title="autocontrol")] \
        == ["autocontrol-dialog", "OK"]
    assert backend.list_elements(window_title="no such window") == []


def test_an_accessible_that_vanishes_mid_walk_is_skipped(monkeypatch):
    """Applications close dialogs while they are being listed."""
    connection = _tree_connection()

    def _explode(reference):
        if reference == BUTTON:
            raise DBusError("no such object")
        return connection.roles.get(reference, "")

    monkeypatch.setattr(connection, "role_name", _explode)
    monkeypatch.setattr(atspi, "_AtspiConnection", lambda: connection)
    instance = atspi.LinuxAccessibilityBackend.__new__(
        atspi.LinuxAccessibilityBackend)
    instance.available = True
    assert [element.name for element in instance.list_elements()] == [
        "autocontrol-dialog"]


def test_a_cyclic_tree_cannot_hang_the_caller(monkeypatch):
    """A malformed tree must bottom out rather than recurse forever."""
    loop = ("app", "/loop")
    connection = FakeConnection(
        tree={("registry", "/root"): [APP], APP: [loop], loop: [loop]},
        names={APP: "app", loop: "loop"}, roles={loop: "panel"})
    monkeypatch.setattr(atspi, "_AtspiConnection", lambda: connection)
    instance = atspi.LinuxAccessibilityBackend.__new__(
        atspi.LinuxAccessibilityBackend)
    instance.available = True
    found = instance.list_elements(max_results=500)
    assert 0 < len(found) < 500


def test_a_nameless_and_roleless_accessible_is_dropped(monkeypatch):
    """A node with neither is not an element a caller could ever address."""
    connection = FakeConnection(
        tree={("registry", "/root"): [APP], APP: [BUTTON]},
        names={APP: "app"}, roles={})
    monkeypatch.setattr(atspi, "_AtspiConnection", lambda: connection)
    instance = atspi.LinuxAccessibilityBackend.__new__(
        atspi.LinuxAccessibilityBackend)
    instance.available = True
    assert instance.list_elements() == []


# --- state -----------------------------------------------------------------


def test_state_reads_both_halves_of_the_bitfield():
    """AT-SPI sends the state as two 32-bit words, not one 64-bit value.

    Reading only the first silently drops every state above bit 31.
    """
    class TwoWordBus:
        def __enter__(self):
            return self

        def __exit__(self, *_exception):
            return None

        def call(self, *_args, **_kwargs):
            # low word carries ENABLED, high word carries bit 32
            return [[1 << 8, 1]]

    connection = atspi._AtspiConnection()
    connection._bus = TwoWordBus()
    assert connection.state(BUTTON) == (1 << 8) | (1 << 32)


# --- control patterns ------------------------------------------------------
#
# The five object-level actions all share one shape: find the reference the
# caller described, then make exactly one AT-SPI call on it. What is worth
# pinning is what happens when the find comes back empty -- every one of them
# has to answer "no", because the caller cannot tell a control that refused
# from a control that was never there, and will otherwise retry forever.


def test_get_value_prefers_the_text_interface(backend):
    backend.connection.texts[BUTTON] = "typed"
    backend.connection.numbers[BUTTON] = 0.5
    assert backend.get_value(name="OK") == "typed"


def test_get_value_falls_back_to_a_numeric_value(backend):
    # A slider has no text; its value is a double on the Value interface.
    backend.connection.numbers[BUTTON] = 0.75
    assert backend.get_value(name="OK") == "0.75"


def test_get_value_of_a_control_with_neither_is_none(backend):
    assert backend.get_value(name="OK") is None


def test_get_value_of_a_control_that_is_not_there_is_none(backend):
    assert backend.get_value(name="Cancel") is None


def test_get_value_can_be_scoped_to_one_application(backend):
    backend.connection.texts[BUTTON] = "typed"
    assert backend.get_value(name="OK", app_name="zenity") == "typed"
    assert backend.get_value(name="OK", app_name="gedit") is None


def test_get_value_matches_a_substring_when_asked(backend):
    # Real interfaces label controls "Save(&S)" and "OK "; exact stays
    # the default, so the same lower-case needle finds nothing without
    # `contains`.
    backend.connection.texts[BUTTON] = "typed"
    assert backend.get_value(name="ok", contains=True) == "typed"
    assert backend.get_value(name="ok") is None


def test_set_value_writes_through_the_editable_interface(backend):
    assert backend.set_value("hello", name="OK") is True
    assert backend.connection.written == [(BUTTON, "hello")]


def test_set_value_on_a_control_that_is_not_there_reports_failure(backend):
    assert backend.set_value("hello", name="Cancel") is False
    assert backend.connection.written == []


def test_set_value_the_control_refuses_reports_failure(backend):
    backend.connection.write_result = False
    assert backend.set_value("hello", name="OK") is False


def test_a_write_that_fails_on_the_bus_reports_failure(backend):
    backend.connection.errors[BUTTON] = DBusError("no EditableText")
    assert backend.set_value("hello", name="OK") is False


def test_invoke_performs_the_first_action(backend):
    assert backend.invoke(name="OK") is True
    assert backend.connection.actions == [(BUTTON, 0)]


def test_invoke_on_a_control_that_is_not_there_reports_failure(backend):
    assert backend.invoke(name="Cancel") is False


def test_an_invoke_that_fails_on_the_bus_reports_failure(backend):
    backend.connection.errors[BUTTON] = DBusError("no Action")
    assert backend.invoke(name="OK") is False


def test_set_focus_grabs_it_through_the_component_interface(backend):
    assert backend.set_focus(name="OK") is True
    assert backend.connection.focused == [BUTTON]


def test_set_focus_on_a_control_that_is_not_there_reports_failure(backend):
    assert backend.set_focus(name="Cancel") is False


def test_a_focus_grab_that_fails_on_the_bus_reports_failure(backend):
    backend.connection.errors[BUTTON] = DBusError("no Component")
    assert backend.set_focus(name="OK") is False


def test_get_state_reports_the_three_bits_it_reads(backend):
    backend.connection.states[BUTTON] = (1 << 8) | (1 << 12) | (1 << 25)
    state = backend.get_state(name="OK")
    assert state == {"enabled": True, "focused": True, "selected": True}


def test_get_state_reports_false_for_bits_that_are_clear(backend):
    backend.connection.states[BUTTON] = 0
    assert backend.get_state(name="OK") == {
        "enabled": False, "focused": False, "selected": False,
    }


def test_get_state_carries_a_value_only_when_the_control_has_one(backend):
    # An absent key and an empty value are different answers: the first says
    # the control has no such concept, the second that it is empty.
    assert "value" not in backend.get_state(name="OK")
    backend.connection.texts[BUTTON] = ""
    assert backend.get_state(name="OK")["value"] == ""


def test_get_state_carries_a_number_only_when_the_control_has_one(backend):
    assert "number" not in backend.get_state(name="OK")
    backend.connection.numbers[BUTTON] = 0.0
    assert backend.get_state(name="OK")["number"] == 0.0


def test_get_state_of_a_control_that_is_not_there_is_none(backend):
    assert backend.get_state(name="Cancel") is None


def test_a_control_pattern_needs_a_backend_that_is_available():
    instance = atspi.LinuxAccessibilityBackend.__new__(
        atspi.LinuxAccessibilityBackend)
    instance.available = False
    for call in (lambda: instance.get_value(name="OK"),
                 lambda: instance.set_value("x", name="OK"),
                 lambda: instance.invoke(name="OK"),
                 lambda: instance.set_focus(name="OK"),
                 lambda: instance.get_state(name="OK")):
        with pytest.raises(AccessibilityNotAvailableError):
            call()


def test_the_search_gives_up_at_a_bounded_depth(monkeypatch):
    """A tree that never ends must not recurse until Python gives up."""
    deep = ("app", "/deep")
    connection = FakeConnection(
        tree={("registry", "/root"): [APP], APP: [deep], deep: [deep]},
        names={APP: "zenity"},
    )
    monkeypatch.setattr(atspi, "_AtspiConnection", lambda: connection)
    instance = atspi.LinuxAccessibilityBackend.__new__(
        atspi.LinuxAccessibilityBackend)
    instance.available = True
    assert instance.get_value(name="nothing here") is None


def test_a_branch_the_bus_refuses_ends_the_search_there(monkeypatch):
    class RefusingConnection(FakeConnection):
        def children(self, reference):
            if reference == APP:
                raise DBusError("BadWindow")
            return super().children(reference)

    connection = RefusingConnection(
        tree={("registry", "/root"): [APP]}, names={APP: "zenity"})
    monkeypatch.setattr(atspi, "_AtspiConnection", lambda: connection)
    instance = atspi.LinuxAccessibilityBackend.__new__(
        atspi.LinuxAccessibilityBackend)
    instance.available = True
    assert instance.get_value(name="OK") is None


def test_an_application_whose_name_cannot_be_read_is_still_walked(monkeypatch):
    class NamelessConnection(FakeConnection):
        def property(self, reference, name, interface=None):
            if reference == APP:
                raise DBusError("gone")
            return super().property(reference, name, interface)

    connection = NamelessConnection(
        tree={("registry", "/root"): [APP], APP: [BUTTON]},
        names={BUTTON: "OK"}, roles={BUTTON: "push button"})
    monkeypatch.setattr(atspi, "_AtspiConnection", lambda: connection)
    instance = atspi.LinuxAccessibilityBackend.__new__(
        atspi.LinuxAccessibilityBackend)
    instance.available = True
    [element] = instance.list_elements()
    assert element.app_name == ""


def test_closing_a_connection_twice_is_harmless():
    """`__exit__` runs on the way out of a `with` and again on a retry."""
    connection = atspi._AtspiConnection()
    connection.__exit__()
    connection.__exit__()
    assert connection._bus is None


def test_the_walk_stops_asking_further_applications_once_it_is_full(
        monkeypatch):
    second = ("other", "/app")
    connection = FakeConnection(
        tree={("registry", "/root"): [APP, second],
              APP: [WINDOW], second: [BUTTON]},
        names={APP: "zenity", WINDOW: "dialog", second: "gedit",
               BUTTON: "OK"},
        roles={WINDOW: "dialog", BUTTON: "push button"},
    )
    monkeypatch.setattr(atspi, "_AtspiConnection", lambda: connection)
    instance = atspi.LinuxAccessibilityBackend.__new__(
        atspi.LinuxAccessibilityBackend)
    instance.available = True
    assert len(instance.list_elements(max_results=1)) == 1


def test_a_branch_the_bus_refuses_ends_that_branch_of_the_walk(monkeypatch):
    class RefusingConnection(FakeConnection):
        def children(self, reference):
            if reference == WINDOW:
                raise DBusError("the dialog closed")
            return super().children(reference)

    connection = RefusingConnection(
        tree={("registry", "/root"): [APP], APP: [WINDOW], WINDOW: [BUTTON]},
        names={APP: "zenity", WINDOW: "dialog", BUTTON: "OK"},
        roles={WINDOW: "dialog", BUTTON: "push button"},
    )
    monkeypatch.setattr(atspi, "_AtspiConnection", lambda: connection)
    instance = atspi.LinuxAccessibilityBackend.__new__(
        atspi.LinuxAccessibilityBackend)
    instance.available = True
    # The window itself was listed before its children were asked for.
    assert [e.name for e in instance.list_elements()] == ["dialog"]


def test_the_walk_stops_mid_application_once_it_is_full(monkeypatch):
    siblings = [("app", f"/b{index}") for index in range(4)]
    connection = FakeConnection(
        tree={("registry", "/root"): [APP], APP: siblings},
        names={APP: "zenity", **{ref: f"b{index}"
                                 for index, ref in enumerate(siblings)}},
        roles={ref: "push button" for ref in siblings},
    )
    monkeypatch.setattr(atspi, "_AtspiConnection", lambda: connection)
    instance = atspi.LinuxAccessibilityBackend.__new__(
        atspi.LinuxAccessibilityBackend)
    instance.available = True
    assert len(instance.list_elements(max_results=2)) == 2
