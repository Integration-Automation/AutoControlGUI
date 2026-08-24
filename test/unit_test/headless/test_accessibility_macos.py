"""Walking the macOS accessibility tree, from any square rather than Darwin.

`backends/macos_backend.py` read 0% everywhere. Its pyobjc imports are inside
the methods, so the module loads on any platform and stubs in `sys.modules`
(`_pyobjc_stub.py`) drive the whole walk from all nine CI squares.

What the walk has to get right:

* **The default scope is the *active* application.** Enumerating every
  running application's whole tree is thousands of nodes for a caller who
  asked about the window in front of them, so an inactive application is
  skipped -- unless it was named, which is the one case where the caller
  clearly meant it.
* **`max_results` bounds the recursion, not just the answer.** The tree is
  deep and the AX API is a round trip per node; a walk that collected
  everything and sliced afterwards would pay for the whole desktop.
* **One application's AX failure must not end the enumeration.** Accessibility
  is granted per process and revoked at any time, and an application that
  refuses is a normal event, not a reason to return nothing.
* **A node with neither role nor title is not an element.** AX reports
  structural nodes with nothing on them; carrying them would fill the answer
  with rows a caller cannot match on.
"""
from __future__ import annotations

import types

import pytest

from headless import _pyobjc_stub as objc_stub
from headless._pyobjc_stub import AX_FAILURE, AXElement
from je_auto_control.utils.accessibility.backends import macos_backend as mac
from je_auto_control.utils.accessibility.backends.macos_backend import (
    MacOSAccessibilityBackend, _extract_bounds,
)
from je_auto_control.utils.accessibility.element import (
    AccessibilityNotAvailableError,
)


class _App:
    """One entry of `NSWorkspace.runningApplications()`."""

    def __init__(self, name: str, pid: int, active: bool = True) -> None:
        self._name = name
        self._pid = pid
        self._active = active

    def isActive(self):         # noqa: N802  # reason: the AppKit name
        return self._active

    def localizedName(self):    # noqa: N802  # reason: the AppKit name
        return self._name

    def processIdentifier(self):    # noqa: N802  # reason: the AppKit name
        return self._pid


def _element(role=None, title=None, position=None, size=None, children=None):
    attributes = {}
    if role is not None:
        attributes["AXRole"] = role
    if title is not None:
        attributes["AXTitle"] = title
    if position is not None:
        attributes["AXPosition"] = position
    if size is not None:
        attributes["AXSize"] = size
    if children is not None:
        attributes["AXChildren"] = children
    return AXElement(**attributes)


class _World(objc_stub.World):
    """The AT-SPI-free half of the pyobjc stub: apps, and a tree per pid."""

    def __init__(self, apps=None, trees=None) -> None:
        super().__init__()
        self.apps = list(apps or [])
        self.trees = dict(trees or {})      # pid -> root AXElement
        self.walk_errors = {}               # pid -> exception

    def ax_application(self, pid):
        if pid in self.walk_errors:
            raise self.walk_errors[pid]
        return self.trees.get(int(pid), AXElement())

    def ax_copy_attribute(self, element, attribute, placeholder):
        # An AX read can raise rather than answer with an error code: the
        # pyobjc bridge turns some failures into exceptions.
        error = getattr(element, "raises", None)
        if error is not None:
            raise error
        return super().ax_copy_attribute(element, attribute, placeholder)


@pytest.fixture
def install(monkeypatch):
    def _install(world: _World) -> MacOSAccessibilityBackend:
        objc_stub.install(monkeypatch, world)
        appkit = types.ModuleType("AppKit")
        appkit.NSWorkspace = types.SimpleNamespace(
            sharedWorkspace=lambda: types.SimpleNamespace(
                runningApplications=lambda: list(world.apps)))
        monkeypatch.setitem(__import__("sys").modules, "AppKit", appkit)
        backend = MacOSAccessibilityBackend()
        assert backend.available
        return backend
    return _install


# --- availability -------------------------------------------------------------

def test_a_mac_without_pyobjc_refuses_and_names_it(monkeypatch):
    monkeypatch.setattr(mac, "_is_available", lambda: False)
    backend = MacOSAccessibilityBackend()
    with pytest.raises(AccessibilityNotAvailableError, match="pyobjc"):
        backend.list_elements()


def test_the_probe_reports_what_it_could_import(monkeypatch):
    import sys
    monkeypatch.setitem(sys.modules, "ApplicationServices",
                        types.ModuleType("ApplicationServices"))
    monkeypatch.setitem(sys.modules, "AppKit", types.ModuleType("AppKit"))
    assert mac._is_available() is True
    monkeypatch.setitem(sys.modules, "ApplicationServices", None)
    assert mac._is_available() is False


def test_the_backend_names_the_api_it_walks(install):
    assert install(_World()).name == "macos-ax"


# --- scoping ------------------------------------------------------------------

def test_only_the_active_application_is_walked_by_default(install):
    world = _World(
        apps=[_App("Safari", 1, active=True), _App("Mail", 2, active=False)],
        trees={1: _element(role="AXWindow", title="Safari window"),
               2: _element(role="AXWindow", title="Mail window")},
    )
    names = [e.name for e in install(world).list_elements()]
    assert names == ["Safari window"]


def test_naming_an_application_reaches_it_even_when_it_is_not_active(install):
    world = _World(
        apps=[_App("Safari", 1, active=True), _App("Mail", 2, active=False)],
        trees={1: _element(role="AXWindow", title="Safari window"),
               2: _element(role="AXWindow", title="Mail window")},
    )
    elements = install(world).list_elements(app_name="Mail")
    assert [e.name for e in elements] == ["Mail window"]
    assert elements[0].app_name == "Mail"


def test_naming_an_application_that_is_not_running_finds_nothing(install):
    world = _World(apps=[_App("Safari", 1)],
                   trees={1: _element(role="AXWindow", title="w")})
    assert install(world).list_elements(app_name="Mail") == []


def test_an_application_with_no_localized_name_is_still_walked(install):
    world = _World(apps=[_App(None, 1)],
                   trees={1: _element(role="AXWindow", title="untitled")})
    [element] = install(world).list_elements()
    assert element.app_name == ""


def test_the_owning_process_is_carried_on_every_element(install):
    world = _World(apps=[_App("Safari", 501)],
                   trees={501: _element(role="AXWindow", title="w")})
    [element] = install(world).list_elements()
    assert element.process_id == 501


# --- the walk -----------------------------------------------------------------

def test_the_walk_is_depth_first_through_the_children(install):
    leaf = _element(role="AXButton", title="OK")
    group = _element(role="AXGroup", title="Buttons", children=[leaf])
    root = _element(role="AXWindow", title="Dialog", children=[group])
    world = _World(apps=[_App("Safari", 1)], trees={1: root})
    names = [e.name for e in install(world).list_elements()]
    assert names == ["Dialog", "Buttons", "OK"]


def test_a_node_with_neither_role_nor_title_is_not_an_element(install):
    structural = _element(children=[_element(role="AXButton", title="OK")])
    world = _World(apps=[_App("Safari", 1)], trees={1: structural})
    names = [e.name for e in install(world).list_elements()]
    assert names == ["OK"], "the structural node is walked through, not listed"


def test_a_node_with_only_a_role_is_still_an_element(install):
    world = _World(apps=[_App("Safari", 1)],
                   trees={1: _element(role="AXWindow")})
    [element] = install(world).list_elements()
    assert (element.role, element.name) == ("AXWindow", "")


def test_the_walk_stops_at_max_results(install):
    children = [_element(role="AXButton", title=f"b{index}")
                for index in range(10)]
    root = _element(role="AXWindow", title="Dialog", children=children)
    world = _World(apps=[_App("Safari", 1)], trees={1: root})
    assert len(install(world).list_elements(max_results=3)) == 3


def test_max_results_bounds_the_recursion_not_just_the_answer(install):
    # Every node is a round trip; collecting the desktop and slicing after
    # would pay for all of it.
    deep = _element(role="AXButton", title="deep")
    nested = _element(role="AXGroup", title="g", children=[deep])
    root = _element(role="AXWindow", title="Dialog", children=[nested])
    world = _World(apps=[_App("Safari", 1)], trees={1: root})
    install(world).list_elements(max_results=1)
    assert "AXChildren" not in nested.attributes or not nested.actions


def test_the_walk_stops_asking_further_applications_once_it_is_full(install):
    world = _World(
        apps=[_App("Safari", 1), _App("Mail", 2)],
        trees={1: _element(role="AXWindow", title="one"),
               2: _element(role="AXWindow", title="two")},
    )
    assert len(install(world).list_elements(max_results=1)) == 1


def test_a_node_that_refuses_to_list_children_ends_that_branch(install):
    root = _element(role="AXWindow", title="Dialog")
    root.read_error = AX_FAILURE
    world = _World(apps=[_App("Safari", 1)], trees={1: root})
    # The node itself cannot be described either, so nothing comes back --
    # and, crucially, no exception does.
    assert install(world).list_elements() == []


def test_a_node_whose_read_raises_is_skipped_rather_than_fatal(install):
    # pyobjc turns some AX failures into exceptions rather than error codes,
    # and a control that vanished mid-walk is an ordinary event.
    root = _element(role="AXWindow", title="Dialog")
    root.raises = RuntimeError("AXError -25202")
    world = _World(apps=[_App("Safari", 1)], trees={1: root})
    assert install(world).list_elements() == []


def test_the_recursion_guard_holds_even_when_entered_full(install):
    # The loop checks before it recurses, so this guard is only reachable by
    # entering the walk with a full list -- which is what makes the helper
    # safe to call from anywhere, including a future second caller.
    world = _World(apps=[_App("Safari", 1)],
                   trees={1: _element(role="AXWindow", title="w")})
    backend = install(world)
    import ApplicationServices as ax_module
    results = ["already full"]
    backend._walk(ax_module, _element(role="AXWindow", title="w"),
                  "Safari", 1, results, max_results=1)
    assert results == ["already full"]


def test_one_application_failing_does_not_end_the_enumeration(install):
    world = _World(
        apps=[_App("Broken", 1), _App("Safari", 2)],
        trees={2: _element(role="AXWindow", title="works")},
    )
    world.walk_errors[1] = RuntimeError("AXError -25211")
    names = [e.name for e in install(world).list_elements(app_name=None)]
    assert names == ["works"]


def test_a_window_title_scope_is_accepted_and_ignored(install):
    # AX walks per application already; returning nothing because the scope
    # cannot be honoured would be worse than returning the unscoped answer.
    world = _World(apps=[_App("Safari", 1)],
                   trees={1: _element(role="AXWindow", title="Dialog")})
    elements = install(world).list_elements(window_title="something else")
    assert [e.name for e in elements] == ["Dialog"]


# --- geometry -----------------------------------------------------------------

def test_an_elements_bounds_come_from_its_position_and_size(install):
    world = _World(apps=[_App("Safari", 1)], trees={
        1: _element(role="AXWindow", title="w", position=(10, 20),
                    size=(300, 400)),
    })
    [element] = install(world).list_elements()
    assert element.bounds == (10, 20, 300, 400)


@pytest.mark.parametrize("position,size", [
    (None, (1, 2)), ((1, 2), None), (None, None),
])
def test_an_element_with_no_geometry_reads_as_the_origin(position, size):
    # A control AX will not place is still worth reporting: the caller can
    # match on its name even if it cannot click it.
    assert _extract_bounds(position, size) == (0, 0, 0, 0)


@pytest.mark.parametrize("position,size", [
    ("not a pair", (1, 2)),
    ((1, 2), "not a pair"),
    ((1,), (1, 2)),
    (("x", "y"), (1, 2)),
])
def test_geometry_that_cannot_be_unpacked_reads_as_the_origin(position, size):
    assert _extract_bounds(position, size) == (0, 0, 0, 0)


def test_geometry_is_narrowed_to_whole_pixels():
    # AX reports floats; bounds are pixels a caller is about to click.
    assert _extract_bounds((1.7, 2.2), (3.9, 4.1)) == (1, 2, 3, 4)
