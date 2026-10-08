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

def test_listing_asks_quartz_for_what_is_on_screen_and_then_for_the_rest(
        backend, world):
    # Two questions, in this order: the on-screen list is the one that comes
    # back front-to-back, so it sets the order; the full list is only mined
    # for windows the first one left out.
    backend.list_windows()
    assert world.list_options == [
        (1 | 16, 0),     # on-screen only, excluding desktop elements
        (0 | 16, 0),     # everything, excluding desktop elements
    ], "both relative to kCGNullWindowID"


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


def test_a_window_quartz_has_never_heard_of_is_not_minimised(backend):
    # This used to answer True, on the reasoning that a minimised window is
    # absent from the on-screen list. It is -- but so is a window that was
    # closed, and now that one window is looked up by id the two can be told
    # apart. The Windows backend answers False for a dead handle too.
    assert backend.is_minimized(7) is False


def test_an_off_screen_window_with_no_element_reads_as_minimised(monkeypatch,
                                                                 on_darwin):
    # Without the Accessibility grant there is no element to ask, and Quartz
    # only knows "not on screen". That is the nearest answer available, and
    # it is the one that makes focus_window try a restore first.
    world = _mac_with_window(ax_windows=[])
    world.off_screen.add(7)
    backend = _build(monkeypatch, world)
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


# --- a minimised window is off screen, not gone -------------------------------
#
# The defect these pin: every lookup of one window went through the on-screen
# list, which a minimised window is not in. `minimize(7)` succeeded, and from
# then on the window was missing from `list_windows` and `restore(7)` raised
# the "grant Accessibility" refusal on a Mac where it had been granted.

def _linked_window(number=7, *, origin=(10, 20), title="Editor"):
    """An accessibility window whose minimising the stub's Quartz notices."""
    element = AXElement(quartz_id=number)
    element.attributes["AXPosition"] = ("point", objc_stub.AXPoint(*origin))
    element.attributes["AXTitle"] = title
    return element


def test_one_window_is_asked_for_by_id_not_searched_for_on_screen(backend,
                                                                  world):
    world.windows = [window_info(7, pid=501)]
    backend.window_process_id(7)
    assert world.list_options == [(objc_stub.OPTION_INCLUDING_WINDOW, 7)]


@pytest.mark.parametrize("window_id", [0, -1])
def test_a_null_window_id_is_not_put_to_quartz(backend, world, window_id):
    # kCGNullWindowID with the including-window option is not a question
    # about a window, so it is answered here rather than asked.
    assert backend.window_process_id(window_id) == 0
    assert world.list_options == []


def test_a_minimised_window_can_be_restored(monkeypatch, on_darwin):
    element = _linked_window()
    world = _mac_with_window(ax_windows=[element])
    backend = _build(monkeypatch, world)
    assert backend.minimize(7) is True
    assert 7 in world.off_screen, "the stub took it off screen, as the Dock does"
    backend.restore(7)
    assert element.attributes["AXMinimized"] is False
    assert 7 not in world.off_screen


def test_a_minimised_window_still_reports_its_owner_and_rectangle(
        monkeypatch, on_darwin):
    world = _mac_with_window(ax_windows=[_linked_window()])
    backend = _build(monkeypatch, world)
    backend.minimize(7)
    assert backend.window_process_id(7) == 501
    assert backend.window_rect(7) == (10, 20, 310, 420)


def test_a_minimised_window_says_it_is_minimised(monkeypatch, on_darwin):
    world = _mac_with_window(ax_windows=[_linked_window()])
    backend = _build(monkeypatch, world)
    assert backend.is_minimized(7) is False
    backend.minimize(7)
    assert backend.is_minimized(7) is True
    backend.restore(7)
    assert backend.is_minimized(7) is False


def test_a_minimised_window_stays_in_the_listing(monkeypatch, on_darwin):
    # What the Windows backend does: EnumWindows + IsWindowVisible keeps an
    # iconified window, so a title search still finds it.
    world = _mac_with_window(ax_windows=[_linked_window()])
    backend = _build(monkeypatch, world)
    backend.minimize(7)
    assert backend.list_windows() == [(7, "Editor")]


def test_minimised_windows_list_after_the_ones_on_screen(monkeypatch,
                                                         on_darwin):
    # Front-most first is the contract; a minimised window is in front of
    # nothing, wherever Quartz happens to put it in the full list.
    world = World(windows=[
        window_info(7, name="Minimised", pid=501, bounds=(10, 20, 300, 400)),
        window_info(3, name="Front", pid=501, bounds=(0, 0, 50, 50)),
        window_info(4, name="Back", pid=99, bounds=(5, 5, 50, 50)),
    ])
    world.ax_windows = {501: [_linked_window(title="Minimised")]}
    backend = _build(monkeypatch, world)
    backend.minimize(7)
    assert backend.list_windows() == [(3, "Front"), (4, "Back"),
                                      (7, "Minimised")]


def test_an_off_screen_window_that_is_not_minimised_is_not_listed(
        monkeypatch, on_darwin):
    # Quartz's full list is mostly not windows anyone minimised: hidden
    # applications, other Spaces, windows built and never shown. Only the
    # accessibility element can say which is which.
    hidden = _linked_window()
    hidden.attributes["AXMinimized"] = False
    world = _mac_with_window(ax_windows=[hidden])
    world.off_screen.add(7)
    backend = _build(monkeypatch, world)
    assert backend.list_windows() == []


def test_an_off_screen_window_with_no_element_is_not_listed(monkeypatch,
                                                            on_darwin):
    # No Accessibility grant: nothing can vouch for the window, and listing
    # every off-screen surface would bury the real ones.
    world = _mac_with_window(ax_windows=[])
    world.off_screen.add(7)
    backend = _build(monkeypatch, world)
    assert backend.list_windows() == []


def test_off_screen_windows_above_the_application_layer_are_not_listed(
        monkeypatch, on_darwin):
    element = _linked_window()
    element.attributes["AXMinimized"] = True
    world = World(windows=[window_info(7, name="Editor", pid=501, layer=25,
                                       bounds=(10, 20, 300, 400))])
    world.ax_windows = {501: [element]}
    world.off_screen.add(7)
    backend = _build(monkeypatch, world)
    assert backend.list_windows() == []


def test_an_off_screen_window_with_no_owner_is_not_listed(monkeypatch,
                                                          on_darwin):
    world = World(windows=[window_info(7, pid=0)])
    world.off_screen.add(7)
    backend = _build(monkeypatch, world)
    assert backend.list_windows() == []


def test_each_application_is_asked_for_its_windows_once(monkeypatch,
                                                        on_darwin):
    # An AX round trip per off-screen window would be dozens for one browser.
    first = _linked_window(7, origin=(10, 20), title="One")
    second = _linked_window(8, origin=(30, 40), title="Two")
    for element in (first, second):
        element.attributes["AXMinimized"] = True
    world = World(windows=[
        window_info(7, name="One", pid=501, bounds=(10, 20, 1, 1)),
        window_info(8, name="Two", pid=501, bounds=(30, 40, 1, 1)),
    ])
    world.ax_windows = {501: [first, second]}
    world.off_screen.update({7, 8})
    asked = []
    real = world.ax_application
    world.ax_application = lambda pid: asked.append(pid) or real(pid)
    backend = _build(monkeypatch, world)
    assert backend.list_windows() == [(7, "One"), (8, "Two")]
    assert asked == [501]


def test_focusing_a_minimised_window_by_title_restores_and_raises_it(
        monkeypatch, on_darwin):
    # The wrapper's whole path: find by title, see it is minimised, restore,
    # raise. Before the fix it stopped at the first step -- "no window
    # matches" -- for a window the same process had just minimised.
    from je_auto_control.wrapper import auto_control_window

    element = _linked_window()
    world = _mac_with_window(ax_windows=[element])
    backend = _build(monkeypatch, world)
    monkeypatch.setattr(auto_control_window, "get_backend", lambda: backend)
    assert auto_control_window.minimize_window_by_title("Editor") is True
    assert 7 in world.off_screen
    assert auto_control_window.focus_window("Editor") == 7
    assert element.attributes["AXMinimized"] is False
    assert element.actions == ["AXRaise"]
