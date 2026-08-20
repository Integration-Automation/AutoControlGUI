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
        return None

    def number(self, reference):
        return None


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
