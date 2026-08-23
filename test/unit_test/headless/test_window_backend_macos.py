"""macOS window management, where reading and acting are two APIs.

`macos_backend.py` was at 0% on every square. Like the X11 one it imports its
platform libraries inside its methods, so stubs in `sys.modules`
(`_pyobjc_stub.py`) exercise it from all nine rather than the two Darwin
squares -- and the coverage floor is the lowest square, so that difference is
the whole point.

The split down the middle of this backend is what the tests are about:

* **Quartz reads, the accessibility API acts**, and they have different
  permission stories. Listing, rectangles and ownership need no grant;
  moving, closing, minimising and raising are gated behind TCC, and until the
  user grants Accessibility every one of them silently does nothing. So each
  action reports refusal rather than a false success.
* **The two APIs do not share a handle.** A `CGWindowID` has no public bridge
  to an `AXUIElement`, so the window is found again inside its owning
  application by origin and then by title. Origin is the stronger signal --
  two windows cannot share one at the same moment, while titles are empty or
  duplicated all the time -- and getting that preference backwards moves the
  wrong window of an application that has several.
* **An AX call returns an error code, and zero is success.** `close()` and
  `minimize()` return `not error`. Reading that backwards is a "yes" for
  every failed action, which is exactly the answer a caller cannot recover
  from.
* **Layer 0 is the application layer.** Menu bars, the Dock and status items
  live above it and are not what anyone means by "the Safari window".

`test_pyobjc_stub_names.py` holds the stub's surface to the real frameworks
wherever they are installed, which on CI is the macOS squares.
"""
from __future__ import annotations

import pytest

from headless import _pyobjc_stub as objc_stub
from headless._pyobjc_stub import AX_FAILURE, AXElement, World, window_info
from je_auto_control.utils.exception.exceptions import (
    AutoControlUnsupportedOperationException,
)
from je_auto_control.wrapper.window_backends import macos_backend as macos
from je_auto_control.wrapper.window_backends.macos_backend import (
    MacOSWindowBackend, _point,
)


@pytest.fixture
def on_darwin(monkeypatch):
    monkeypatch.setattr(macos.sys, "platform", "darwin")


def _build(monkeypatch, world: World) -> MacOSWindowBackend:
    objc_stub.install(monkeypatch, world)
    backend = MacOSWindowBackend()
    assert backend.available, "the stubbed frameworks import"
    return backend


@pytest.fixture
def world():
    return World()


@pytest.fixture
def backend(monkeypatch, on_darwin, world):
    return _build(monkeypatch, world)


# --- availability -------------------------------------------------------------

def test_the_backend_is_unavailable_off_macos(monkeypatch, world):
    monkeypatch.setattr(macos.sys, "platform", "linux")
    objc_stub.install(monkeypatch, world)
    assert MacOSWindowBackend().available is False


def test_a_mac_without_pyobjc_is_unavailable_rather_than_fatal(monkeypatch,
                                                               on_darwin):
    # pyobjc is a hard dependency on Darwin, but a broken or partial install
    # must degrade to the null backend, not to an ImportError at start-up.
    objc_stub.install_missing(monkeypatch, "Quartz")
    assert MacOSWindowBackend().available is False


def test_the_backend_names_both_apis_it_uses(backend):
    assert backend.name == "macos-quartz-ax"


# --- listing ------------------------------------------------------------------

def test_listing_asks_quartz_for_on_screen_windows_only(backend, world):
    backend.list_windows()
    [(options, relative_to)] = world.list_options
    assert options == 1 | 16, "on-screen only, excluding desktop elements"
    assert relative_to == 0, "kCGNullWindowID"


def test_listing_keeps_the_order_quartz_gives(backend, world):
    # Quartz returns front-to-back, which is already what a caller means by
    # "the first window that matches".
    world.windows = [window_info(3, name="front"), window_info(1, name="back")]
    assert backend.list_windows() == [(3, "front"), (1, "back")]


def test_listing_skips_everything_above_the_application_layer(backend, world):
    world.windows = [window_info(1, name="Menubar", layer=25),
                     window_info(2, name="Editor", layer=0)]
    assert backend.list_windows() == [(2, "Editor")]


def test_listing_skips_a_window_with_no_id(backend, world):
    # Quartz omits the number for windows a caller has no business addressing.
    world.windows = [window_info(0, name="anonymous")]
    assert backend.list_windows() == []


def test_a_window_with_no_title_lists_with_an_empty_one(backend, world):
    # Screen-recording permission is what puts titles in this list; without
    # it Quartz still reports the windows, with the names left out.
    world.windows = [{"kCGWindowNumber": 7, "kCGWindowLayer": 0}]
    assert backend.list_windows() == [(7, "")]


def test_a_desktop_quartz_answers_nothing_for_lists_nothing(backend, world):
    world.windows = []
    assert backend.list_windows() == []


# --- the focused window -------------------------------------------------------

def test_the_foreground_window_is_the_front_one_of_the_front_app(backend,
                                                                 world):
    world.frontmost_pid = 501
    world.windows = [window_info(1, pid=99), window_info(2, pid=501),
                     window_info(3, pid=501)]
    assert backend.foreground_window() == 2, "front-to-back, so the first"


def test_no_frontmost_application_reads_as_no_window(backend, world):
    world.frontmost_pid = None
    assert backend.foreground_window() == 0


def test_a_frontmost_app_with_no_ordinary_window_reads_as_none(backend,
                                                               world):
    world.frontmost_pid = 501
    world.windows = [window_info(1, pid=501, layer=25)]
    assert backend.foreground_window() == 0


# --- rectangles and ownership -------------------------------------------------

def test_the_rectangle_is_the_bounds_quartz_reports(backend, world):
    world.windows = [window_info(7, bounds=(100, 200, 640, 480))]
    assert backend.window_rect(7) == (100, 200, 740, 680)


def test_a_rectangle_for_a_window_that_is_gone_is_none(backend, world):
    # The lookup walks the whole list before giving up, so an unrelated
    # window in front of it is the ordinary case, not an edge one.
    world.windows = [window_info(9, bounds=(0, 0, 1, 1))]
    assert backend.window_rect(7) is None


def test_a_window_quartz_reports_without_bounds_has_no_rectangle(backend,
                                                                 world):
    world.windows = [window_info(7)]
    assert backend.window_rect(7) is None


def test_the_owning_pid_comes_from_the_window_info(backend, world):
    world.windows = [window_info(7, pid=501)]
    assert backend.window_process_id(7) == 501


def test_a_window_that_is_gone_has_no_owner(backend, world):
    assert backend.window_process_id(7) == 0


# --- matching a Quartz window to an accessibility element ---------------------

def _mac_with_window(number=7, *, pid=501, name="Editor",
                     bounds=(10, 20, 300, 400), ax_windows=None,
                     running=True):
    world = World(windows=[window_info(number, name=name, pid=pid,
                                       bounds=bounds)],
                  running_pids={pid} if running else set())
    world.ax_windows = {pid: list(ax_windows or [])}
    return world


def _ax_window(origin=None, title=None):
    attributes = {}
    if origin is not None:
        attributes["AXPosition"] = ("point", objc_stub.AXPoint(*origin))
    if title is not None:
        attributes["AXTitle"] = title
    return AXElement(**attributes)


def test_the_element_is_matched_by_its_origin(monkeypatch, on_darwin):
    wanted = _ax_window(origin=(10, 20))
    world = _mac_with_window(ax_windows=[_ax_window(origin=(99, 99)), wanted])
    backend = _build(monkeypatch, world)
    assert backend._ax_window(7) is wanted


def test_the_title_is_only_the_fallback(monkeypatch, on_darwin):
    # Two windows cannot share an origin at one moment; they share titles all
    # the time, so the frame is tried first and the title only after.
    by_origin = _ax_window(origin=(10, 20), title="Other")
    by_title = _ax_window(origin=(0, 0), title="Editor")
    world = _mac_with_window(ax_windows=[by_title, by_origin])
    backend = _build(monkeypatch, world)
    assert backend._ax_window(7) is by_origin


def test_a_title_match_is_used_when_no_origin_matches(monkeypatch, on_darwin):
    by_title = _ax_window(origin=(0, 0), title="Editor")
    world = _mac_with_window(ax_windows=[by_title])
    backend = _build(monkeypatch, world)
    assert backend._ax_window(7) is by_title


def test_an_untitled_quartz_window_is_not_matched_by_an_empty_title(
        monkeypatch, on_darwin):
    # Matching "" against "" would pick an arbitrary window of the app.
    candidate = _ax_window(origin=(0, 0), title="")
    world = _mac_with_window(name="", ax_windows=[candidate])
    backend = _build(monkeypatch, world)
    assert backend._ax_window(7) is None


def test_an_element_with_no_readable_position_is_skipped(monkeypatch,
                                                         on_darwin):
    unreadable = _ax_window(title="Editor")
    world = _mac_with_window(ax_windows=[unreadable])
    backend = _build(monkeypatch, world)
    assert backend._ax_window(7) is unreadable, "found by title instead"


def test_a_window_quartz_does_not_know_has_no_element(backend):
    assert backend._ax_window(7) is None


def test_a_window_with_no_owner_has_no_element(monkeypatch, on_darwin):
    world = World(windows=[window_info(7, pid=0)])
    backend = _build(monkeypatch, world)
    assert backend._ax_window(7) is None


def test_an_application_that_refuses_to_list_windows_yields_nothing(
        monkeypatch, on_darwin):
    world = _mac_with_window(ax_windows=[_ax_window(origin=(10, 20))])
    world.ax_list_error = AX_FAILURE
    backend = _build(monkeypatch, world)
    assert backend._ax_window(7) is None


@pytest.mark.parametrize("value,expected", [
    (None, (-1, -1)),
    (("size", objc_stub.AXSize(1, 2)), (-1, -1)),
    (("point", objc_stub.AXPoint(3, 4)), (3, 4)),
])
def test_an_ax_point_reads_as_a_pair_or_as_nothing(monkeypatch, on_darwin,
                                                   world, value, expected):
    objc_stub.install(monkeypatch, world)
    assert _point(value) == expected


# --- minimised state ----------------------------------------------------------

def test_a_window_the_element_says_is_minimised_is_minimised(monkeypatch,
                                                             on_darwin):
    element = _ax_window(origin=(10, 20))
    element.attributes["AXMinimized"] = True
    world = _mac_with_window(ax_windows=[element])
    backend = _build(monkeypatch, world)
    assert backend.is_minimized(7) is True


def test_a_window_the_element_says_is_not_minimised_is_not(monkeypatch,
                                                           on_darwin):
    element = _ax_window(origin=(10, 20))
    element.attributes["AXMinimized"] = False
    world = _mac_with_window(ax_windows=[element])
    backend = _build(monkeypatch, world)
    assert backend.is_minimized(7) is False


def test_a_window_that_is_not_on_screen_at_all_is_minimised(backend):
    # A minimised window is absent from the on-screen list, so failing to
    # find it is itself the answer rather than an error.
    assert backend.is_minimized(7) is True


def test_a_window_on_screen_with_no_element_is_not_minimised(monkeypatch,
                                                             on_darwin):
    world = _mac_with_window(ax_windows=[])
    backend = _build(monkeypatch, world)
    assert backend.is_minimized(7) is False


# --- raising ------------------------------------------------------------------

def test_raising_activates_the_app_and_then_the_window(monkeypatch,
                                                       on_darwin):
    element = _ax_window(origin=(10, 20))
    world = _mac_with_window(ax_windows=[element])
    backend = _build(monkeypatch, world)
    backend.set_foreground(7)
    assert world.activated == [(501, 2)], "ignoring other apps"
    assert element.actions == ["AXRaise"], (
        "activating brings the app's front window forward, not this one"
    )


def test_raising_a_window_with_no_owner_is_refused(monkeypatch, on_darwin):
    world = World(windows=[window_info(7, pid=0)])
    backend = _build(monkeypatch, world)
    with pytest.raises(AutoControlUnsupportedOperationException,
                       match="set_foreground"):
        backend.set_foreground(7)


def test_raising_still_raises_when_the_app_object_is_gone(monkeypatch,
                                                          on_darwin):
    # The application can quit between the pid lookup and the activation,
    # which leaves nothing to activate but still an element to raise.
    element = _ax_window(origin=(10, 20))
    world = _mac_with_window(ax_windows=[element], running=False)
    backend = _build(monkeypatch, world)
    backend.set_foreground(7)
    assert world.activated == []
    assert element.actions == ["AXRaise"]


def test_raising_a_window_the_accessibility_api_cannot_find_still_activates(
        monkeypatch, on_darwin):
    # Without Accessibility there is no element, but the application can
    # still be brought forward -- which is most of what the user asked for.
    world = _mac_with_window(ax_windows=[])
    backend = _build(monkeypatch, world)
    backend.set_foreground(7)
    assert world.activated == [(501, 2)]


# --- restoring and show-state codes -------------------------------------------

def test_restoring_clears_the_minimised_attribute(monkeypatch, on_darwin):
    element = _ax_window(origin=(10, 20))
    element.attributes["AXMinimized"] = True
    world = _mac_with_window(ax_windows=[element])
    backend = _build(monkeypatch, world)
    backend.restore(7)
    assert element.attributes["AXMinimized"] is False


def test_restoring_a_window_with_no_element_says_why(monkeypatch, on_darwin):
    # This is the TCC case: without Accessibility there is no element, and a
    # silent no-op would look like a window that refused to restore.
    world = _mac_with_window(ax_windows=[])
    backend = _build(monkeypatch, world)
    with pytest.raises(AutoControlUnsupportedOperationException,
                       match="Accessibility"):
        backend.restore(7)


@pytest.mark.parametrize("code", [macos.SW_SHOWNORMAL, macos.SW_RESTORE])
def test_the_normal_and_restore_codes_both_restore(monkeypatch, on_darwin,
                                                   code):
    element = _ax_window(origin=(10, 20))
    element.attributes["AXMinimized"] = True
    world = _mac_with_window(ax_windows=[element])
    backend = _build(monkeypatch, world)
    backend.show(7, code)
    assert element.attributes["AXMinimized"] is False


@pytest.mark.parametrize("code", [macos.SW_MINIMIZE, macos.SW_SHOWMINIMIZED])
def test_both_minimise_codes_minimise(monkeypatch, on_darwin, code):
    element = _ax_window(origin=(10, 20))
    world = _mac_with_window(ax_windows=[element])
    backend = _build(monkeypatch, world)
    backend.show(7, code)
    assert element.attributes["AXMinimized"] is True


@pytest.mark.parametrize("code", [0, 3, 8])
def test_a_show_code_with_no_macos_meaning_is_refused(backend, code):
    # macOS has no hide-this-window and no maximise-this-window; zoom is not
    # maximise, and the difference matters to the caller.
    with pytest.raises(AutoControlUnsupportedOperationException,
                       match="show"):
        backend.show(7, code)


# --- closing and minimising ---------------------------------------------------

def test_closing_presses_the_windows_own_close_button(monkeypatch, on_darwin):
    button = AXElement()
    element = _ax_window(origin=(10, 20))
    element.attributes["AXCloseButton"] = button
    world = _mac_with_window(ax_windows=[element])
    backend = _build(monkeypatch, world)
    assert backend.close(7) is True
    assert button.actions == ["AXPress"]


def test_a_close_the_accessibility_api_refuses_reports_failure(monkeypatch,
                                                               on_darwin):
    # AX answers with an error code where zero is success, so this is the
    # test that would fail if that were read the other way round.
    button = AXElement()
    button.action_error = AX_FAILURE
    element = _ax_window(origin=(10, 20))
    element.attributes["AXCloseButton"] = button
    world = _mac_with_window(ax_windows=[element])
    backend = _build(monkeypatch, world)
    assert backend.close(7) is False


def test_a_window_with_no_close_button_cannot_be_closed(monkeypatch,
                                                        on_darwin):
    world = _mac_with_window(ax_windows=[_ax_window(origin=(10, 20))])
    backend = _build(monkeypatch, world)
    assert backend.close(7) is False


def test_closing_a_window_with_no_element_reports_failure(backend):
    assert backend.close(7) is False


def test_minimising_sets_the_attribute(monkeypatch, on_darwin):
    element = _ax_window(origin=(10, 20))
    world = _mac_with_window(ax_windows=[element])
    backend = _build(monkeypatch, world)
    assert backend.minimize(7) is True
    assert element.attributes["AXMinimized"] is True


def test_a_minimise_the_accessibility_api_refuses_reports_failure(monkeypatch,
                                                                  on_darwin):
    element = _ax_window(origin=(10, 20))
    element.set_error = AX_FAILURE
    world = _mac_with_window(ax_windows=[element])
    backend = _build(monkeypatch, world)
    assert backend.minimize(7) is False


def test_minimising_a_window_with_no_element_reports_failure(backend):
    assert backend.minimize(7) is False


# --- moving -------------------------------------------------------------------

def test_moving_sets_position_and_size_as_ax_values(monkeypatch, on_darwin):
    element = _ax_window(origin=(10, 20))
    world = _mac_with_window(ax_windows=[element])
    backend = _build(monkeypatch, world)
    assert backend.move(7, 100, 200, 640, 480) is True
    written = dict(element.assignments)
    kind, point = written["AXPosition"]
    assert (kind, point.x, point.y) == ("point", 100.0, 200.0)
    kind, size = written["AXSize"]
    assert (kind, size.width, size.height) == ("size", 640.0, 480.0)


def test_a_move_the_accessibility_api_refuses_reports_failure(monkeypatch,
                                                              on_darwin):
    element = _ax_window(origin=(10, 20))
    element.set_error = AX_FAILURE
    world = _mac_with_window(ax_windows=[element])
    backend = _build(monkeypatch, world)
    assert backend.move(7, 0, 0, 10, 10) is False


def test_moving_a_window_with_no_element_reports_failure(backend):
    assert backend.move(7, 0, 0, 10, 10) is False


# --- what macOS deliberately will not do --------------------------------------

@pytest.mark.parametrize("call", [
    lambda b: b.post_key(7, 38),
    lambda b: b.post_click(7, "left", 0, 0),
])
def test_input_to_an_unfocused_window_is_refused_not_faked(backend, call):
    # macOS has no PostMessage and no XSendEvent: an event goes wherever the
    # focus is. A "success" that clicked somewhere else is worse than a no.
    with pytest.raises(AutoControlUnsupportedOperationException):
        call(backend)
