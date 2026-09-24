"""Registering a hotkey on Windows and on macOS, and picking a backend.

The X11 half is in `test_hotkey_backend_linux.py`. These two do the same job
through completely different machinery -- `RegisterHotKey` plus a message
pump on Windows, a `CGEventTap` plus a run loop on macOS -- and both sat at
around 12% and 41%.

Neither needed a desktop. The Windows backend takes `user32` as an *argument*
to the three methods that do the work, so a recorder drives them anywhere;
only the prologue that builds it needs `ctypes.wintypes`, and that part is
marked Windows-only. The macOS one imports Quartz and CoreFoundation inside
its loop, so stubs in `sys.modules` reach it.

What the two share, and what these tests are about:

* **Sync is a diff, not a re-registration.** A binding whose combo has not
  changed must not be unregistered and registered again on every poll --
  that is a window during which the hotkey does not work, four times a
  second.
* **A combo the parser rejects must not take the others down.** Bindings come
  from a user-edited file; one bad line is normal.
* **The teardown has to release what it took.** An OS-level hotkey survives
  the process that registered it on neither platform, but a leaked
  registration inside a long-lived daemon means a key that is swallowed and
  fires nothing.
* **macOS consumes the event by returning None from the tap** and defers the
  actual firing to the polling thread, because the tap callback runs on the
  run loop and calling a user script there would block every key on the
  system until it finished.
"""
from __future__ import annotations

import sys
import threading
import types

import pytest

from je_auto_control.utils.hotkey import backends as backends_mod
from je_auto_control.utils.hotkey.backends import macos_backend as mac
from je_auto_control.utils.hotkey.backends.macos_backend import (
    MacOSHotkeyBackend, _combo_to_macos, _primary_key_to_keycode,
)
from je_auto_control.utils.hotkey.backends.windows_backend import (
    WindowsHotkeyBackend,
)
from je_auto_control.utils.hotkey.hotkey_daemon import (
    BackendContext, HotkeyBinding, parse_combo,
)


def _binding(binding_id="b1", combo="ctrl+alt+k"):
    return HotkeyBinding(binding_id=binding_id, combo=combo,
                         script_path="script.json")


def _context(bindings, fired=None, stop_after=1):
    stop = threading.Event()
    state = {"polls": 0}

    def _get_bindings():
        state["polls"] += 1
        if state["polls"] >= stop_after:
            stop.set()
        return list(bindings)

    return BackendContext(stop_event=stop, get_bindings=_get_bindings,
                          fire=(fired if fired is not None else []).append)


# --- the selector -------------------------------------------------------------

@pytest.fixture
def on_platform(monkeypatch):
    def _set(name: str):
        monkeypatch.setattr(backends_mod.sys, "platform", name)
    return _set


@pytest.mark.parametrize("platform,expected", [
    ("win32", "windows"), ("darwin", "macos"), ("linux", "linux-x11"),
    ("linux2", "linux-x11"),
])
def test_each_platform_gets_its_own_backend(on_platform, platform, expected):
    on_platform(platform)
    assert backends_mod.get_backend().name == expected


def test_a_platform_with_no_hotkey_backend_says_so(on_platform):
    # Unlike the accessibility and window seams there is no null backend
    # here: a daemon that silently registered nothing would look like a
    # daemon whose hotkeys never fire.
    on_platform("sunos5")
    with pytest.raises(NotImplementedError, match="sunos5"):
        backends_mod.get_backend()


# --- Windows: RegisterHotKey --------------------------------------------------

class _User32:
    """The three user32 entry points the backend calls, as a recorder."""

    def __init__(self, register_result=True) -> None:
        self.registered = []
        self.unregistered = []
        self.register_result = register_result
        self.RegisterHotKey = _Stub(self._register)      # noqa: N815
        self.UnregisterHotKey = _Stub(self._unregister)  # noqa: N815
        self.PeekMessageW = _Stub(lambda *args: 0)       # noqa: N815

    def _register(self, hwnd, reg_id, modifiers, vk):
        self.registered.append((reg_id, modifiers, vk))
        return 1 if self.register_result else 0

    def _unregister(self, hwnd, reg_id):
        self.unregistered.append(reg_id)
        return 1

    @property
    def held(self):
        """Registration ids still outstanding, in the order they were taken."""
        out = [reg_id for reg_id, _mods, _vk in self.registered]
        for reg_id in self.unregistered:
            if reg_id in out:
                out.remove(reg_id)
        return out


class _Stub:
    """A user32 function pointer: callable, and it accepts argtypes/restype."""

    def __init__(self, call) -> None:
        self._call = call
        self.argtypes = None
        self.restype = None

    def __call__(self, *args):
        return self._call(*args)


@pytest.fixture
def user32():
    return _User32()


@pytest.fixture
def win_backend():
    return WindowsHotkeyBackend()


def test_a_new_binding_is_registered_with_its_parsed_combo(win_backend,
                                                            user32):
    win_backend._sync(user32, [_binding()])
    [(_reg_id, modifiers, vk)] = user32.registered
    assert (modifiers, vk) == parse_combo("ctrl+alt+k")


def test_each_registration_gets_its_own_id(win_backend, user32):
    win_backend._sync(user32, [_binding("b1", "ctrl+k"),
                               _binding("b2", "ctrl+q")])
    ids = [reg_id for reg_id, _m, _v in user32.registered]
    assert len(set(ids)) == 2


def test_a_binding_that_has_not_changed_is_not_re_registered(win_backend,
                                                              user32):
    bindings = [_binding()]
    win_backend._sync(user32, bindings)
    win_backend._sync(user32, bindings)
    assert len(user32.registered) == 1
    assert user32.unregistered == [], "the hotkey never stopped working"


def test_a_binding_whose_combo_changed_releases_the_old_key(win_backend,
                                                             user32):
    win_backend._sync(user32, [_binding(combo="ctrl+k")])
    first_id = user32.registered[0][0]
    win_backend._sync(user32, [_binding(combo="ctrl+q")])
    assert first_id in user32.unregistered
    assert len(user32.held) == 1


def test_a_binding_that_disappeared_is_unregistered(win_backend, user32):
    win_backend._sync(user32, [_binding()])
    win_backend._sync(user32, [])
    assert user32.held == []
    assert win_backend._registered == {}


def test_an_unparseable_combo_is_logged_and_skipped(win_backend, user32):
    win_backend._sync(user32, [_binding(combo="ctrl+"), _binding("b2", "ctrl+k")])
    assert list(win_backend._registered) == ["b2"]


def test_a_registration_windows_refuses_is_not_remembered(win_backend):
    # Another application already owns the combo. Remembering it would mean
    # never retrying, and reporting it as bound would be a lie.
    refusing = _User32(register_result=False)
    win_backend._sync(refusing, [_binding()])
    assert win_backend._registered == {}


def test_a_hotkey_message_fires_the_binding_it_belongs_to(win_backend,
                                                           user32):
    win_backend._sync(user32, [_binding("b1", "ctrl+k"),
                               _binding("b2", "ctrl+q")])
    second_id = user32.registered[1][0]
    fired = []
    win_backend._dispatch(second_id, fired.append)
    assert fired == ["b2"]


def test_a_hotkey_message_for_an_unknown_id_fires_nothing(win_backend,
                                                           user32):
    win_backend._sync(user32, [_binding()])
    fired = []
    win_backend._dispatch(9999, fired.append)
    assert fired == []


@pytest.mark.skipif(sys.platform != "win32",
                    reason="ctypes.wintypes is Windows-only")
def test_the_message_pump_registers_and_releases(monkeypatch, win_backend):
    import ctypes
    recorder = _User32()
    monkeypatch.setattr(ctypes, "WinDLL",
                        lambda name, **kwargs: recorder)
    win_backend.run_forever(_context([_binding()]))
    assert recorder.registered, "it registered while running"
    assert recorder.held == [], "and released on the way out"
    assert win_backend._registered == {}


@pytest.mark.skipif(sys.platform != "win32",
                    reason="ctypes.wintypes is Windows-only")
def test_a_hotkey_message_reaches_the_binding_through_the_pump(monkeypatch,
                                                               win_backend):
    import ctypes
    recorder = _User32()
    messages = {"left": 1}

    def _peek(msg_pointer, hwnd, low, high, remove):
        if not messages["left"]:
            return 0
        messages["left"] -= 1
        msg = msg_pointer._obj
        msg.message = 0x0312       # WM_HOTKEY
        msg.wParam = recorder.registered[0][0]
        return 1

    recorder.PeekMessageW = _Stub(_peek)
    monkeypatch.setattr(ctypes, "WinDLL", lambda name, **kwargs: recorder)
    fired = []
    win_backend.run_forever(_context([_binding()], fired))
    assert fired == ["b1"]


@pytest.mark.skipif(sys.platform != "win32",
                    reason="ctypes.wintypes is Windows-only")
def test_a_message_that_is_not_a_hotkey_is_pumped_past(monkeypatch,
                                                       win_backend):
    # The queue carries whatever Windows posts to the thread; only WM_HOTKEY
    # means one of ours fired.
    import ctypes
    recorder = _User32()
    messages = {"left": 2}

    def _peek(msg_pointer, hwnd, low, high, remove):
        if not messages["left"]:
            return 0
        messages["left"] -= 1
        msg = msg_pointer._obj
        msg.message = 0x0113 if messages["left"] else 0x0312   # WM_TIMER
        msg.wParam = recorder.registered[0][0]
        return 1

    recorder.PeekMessageW = _Stub(_peek)
    monkeypatch.setattr(ctypes, "WinDLL", lambda name, **kwargs: recorder)
    fired = []
    win_backend.run_forever(_context([_binding()], fired))
    assert fired == ["b1"], "the timer was skipped, the hotkey was not"


def test_the_windows_backend_names_the_api_it_uses(win_backend):
    assert win_backend.name == "windows"


# --- macOS: CGEventTap --------------------------------------------------------

_FLAG_SHIFT = 1 << 17
_FLAG_CONTROL = 1 << 18
_FLAG_ALT = 1 << 19
_FLAG_CMD = 1 << 20


@pytest.mark.parametrize("combo,mask", [
    ("k", 0),
    ("ctrl+k", _FLAG_CONTROL),
    ("shift+k", _FLAG_SHIFT),
    ("alt+k", _FLAG_ALT),
    ("win+k", _FLAG_CMD),
    ("ctrl+alt+k", _FLAG_CONTROL | _FLAG_ALT),
])
def test_a_combo_becomes_a_quartz_flags_mask(combo, mask):
    assert _combo_to_macos(combo)[0] == mask


@pytest.mark.parametrize("key,keycode", [
    ("a", 0), ("z", 6), ("m", 46),          # letters
    ("1", 18), ("6", 22), ("0", 29),        # digits, in Carbon's odd order
    ("return", 36), ("enter", 36), ("space", 49), ("esc", 53),
    ("escape", 53), ("f1", 122), ("f12", 111), ("pageup", 116),
    ("A", 0), ("F1", 122),                  # case does not matter
])
def test_a_key_name_becomes_a_carbon_virtual_keycode(key, keycode):
    assert _primary_key_to_keycode(key) == keycode


def test_a_key_carbon_has_no_code_for_is_refused():
    with pytest.raises(ValueError, match="unsupported hotkey key"):
        _primary_key_to_keycode("mediaplay")


@pytest.fixture
def mac_backend():
    return MacOSHotkeyBackend()


def test_a_new_binding_is_remembered_with_its_mask_and_keycode(mac_backend):
    mac_backend._sync([_binding()])
    assert mac_backend._registered == {
        "b1": ("ctrl+alt+k", _FLAG_CONTROL | _FLAG_ALT, 40),
    }


def test_a_binding_that_has_not_changed_is_left_alone(mac_backend):
    bindings = [_binding()]
    mac_backend._sync(bindings)
    first = mac_backend._registered["b1"]
    mac_backend._sync(bindings)
    assert mac_backend._registered["b1"] is first


def test_a_binding_whose_combo_changed_is_replaced(mac_backend):
    mac_backend._sync([_binding(combo="ctrl+k")])
    mac_backend._sync([_binding(combo="ctrl+q")])
    assert mac_backend._registered["b1"][0] == "ctrl+q"


def test_a_binding_that_disappeared_is_forgotten(mac_backend):
    mac_backend._sync([_binding()])
    mac_backend._sync([])
    assert mac_backend._registered == {}


def test_an_unparseable_combo_is_logged_and_skipped_on_macos(mac_backend):
    mac_backend._sync([_binding(combo="ctrl+mediaplay"),
                       _binding("b2", "ctrl+k")])
    assert list(mac_backend._registered) == ["b2"]


def test_a_matching_key_event_names_its_binding(mac_backend):
    mac_backend._sync([_binding()])
    assert mac_backend._match(40, _FLAG_CONTROL | _FLAG_ALT) == "b1"


def test_an_event_with_extra_modifiers_does_not_match(mac_backend):
    mac_backend._sync([_binding(combo="ctrl+k")])
    assert mac_backend._match(40, _FLAG_CONTROL | _FLAG_SHIFT) is None


def test_an_event_for_another_key_does_not_match(mac_backend):
    mac_backend._sync([_binding()])
    assert mac_backend._match(99, _FLAG_CONTROL | _FLAG_ALT) is None


def test_pending_fires_are_drained_in_order(mac_backend):
    mac_backend._pending_fires = ["b1", "b2"]
    fired = []
    mac_backend._drain_fires(fired.append)
    assert fired == ["b1", "b2"]
    assert mac_backend._pending_fires == []


# --- the macOS run loop -------------------------------------------------------

class _Quartz(types.ModuleType):
    """The Quartz surface the tap setup touches."""

    kCGKeyboardEventKeycode = "keycode"     # noqa: N815  # reason: Quartz name
    kCGEventKeyDown = 10                    # noqa: N815
    kCGHIDEventTap = 0                      # noqa: N815
    kCGHeadInsertEventTap = 0               # noqa: N815
    kCGEventTapOptionDefault = 0            # noqa: N815

    def __init__(self, tap="tap") -> None:
        super().__init__("Quartz")
        self.tap = tap
        self.enabled = []
        self.sources_added = []
        self.sources_removed = []
        self.callback = None
        self.tap_mask = None

    def CGEventGetIntegerValueField(self, event, field):    # noqa: N802
        return event["keycode"]

    def CGEventGetFlags(self, event):       # noqa: N802  # reason: Quartz name
        return event["flags"]

    def CGEventTapCreate(self, tap_point, place, options, mask,  # noqa: N802
                         callback, refcon):
        self.callback = callback
        self.tap_mask = mask
        return self.tap

    def CFMachPortCreateRunLoopSource(self, allocator, tap, order):  # noqa: N802
        return "source"

    def CFRunLoopGetCurrent(self):          # noqa: N802  # reason: Quartz name
        return "run-loop"

    def CFRunLoopAddSource(self, loop, source, mode):    # noqa: N802
        self.sources_added.append((loop, source, mode))

    def CFRunLoopRemoveSource(self, loop, source, mode):  # noqa: N802
        self.sources_removed.append((loop, source, mode))

    def CGEventTapEnable(self, tap, enable):    # noqa: N802
        self.enabled.append(bool(enable))


@pytest.fixture
def quartz(monkeypatch):
    def _install(tap="tap"):
        module = _Quartz(tap)
        monkeypatch.setitem(sys.modules, "Quartz", module)
        core = types.ModuleType("CoreFoundation")
        core.kCFRunLoopDefaultMode = "default-mode"
        core.CFRunLoopRunInMode = lambda mode, seconds, once: None
        monkeypatch.setitem(sys.modules, "CoreFoundation", core)
        return module
    return _install


def test_the_tap_listens_for_key_down_only(mac_backend, quartz):
    module = quartz()
    mac_backend.run_forever(_context([_binding()]))
    assert module.tap_mask == 1 << module.kCGEventKeyDown


def test_the_tap_is_enabled_while_running_and_disabled_after(mac_backend,
                                                              quartz):
    module = quartz()
    mac_backend.run_forever(_context([_binding()]))
    assert module.enabled == [True, False]
    assert module.sources_added and module.sources_removed


def test_a_mac_without_accessibility_permission_gives_up_with_a_reason(
        mac_backend, quartz):
    # `CGEventTapCreate` returns None rather than failing when the grant is
    # missing, so this is the only signal there is.
    module = quartz(tap=None)
    mac_backend.run_forever(_context([_binding()]))
    assert module.enabled == [], "nothing to enable, and nothing to remove"


def test_a_mac_without_pyobjc_gives_up_quietly(mac_backend, monkeypatch):
    monkeypatch.setitem(sys.modules, "Quartz", None)
    mac_backend.run_forever(_context([_binding()]))
    assert mac_backend._registered == {}


def test_a_matching_key_is_consumed_and_queued(mac_backend, quartz):
    # Returning None consumes the event; the fire is deferred to the polling
    # thread because the callback runs on the run loop, where calling a user
    # script would block every key on the system.
    module = quartz()
    fired = []
    mac_backend.run_forever(_context([_binding()], fired, stop_after=2))
    event = {"keycode": 40, "flags": _FLAG_CONTROL | _FLAG_ALT}
    assert module.callback(None, None, event, None) is None
    mac_backend._drain_fires(fired.append)
    assert fired == ["b1"]


def test_a_key_that_matches_nothing_is_passed_through(mac_backend, quartz):
    module = quartz()
    mac_backend.run_forever(_context([_binding()]))
    event = {"keycode": 99, "flags": 0}
    assert module.callback(None, None, event, None) is event


def test_an_unrelated_modifier_bit_is_masked_off_before_matching(mac_backend,
                                                                  quartz):
    # macOS sets bits for caps lock, the numeric keypad and more; only the
    # four modifier flags take part in the comparison.
    module = quartz()
    mac_backend.run_forever(_context([_binding()]))
    event = {"keycode": 40,
             "flags": _FLAG_CONTROL | _FLAG_ALT | (1 << 16) | (1 << 21)}
    assert module.callback(None, None, event, None) is None


def test_the_macos_backend_names_the_api_it_uses(mac_backend):
    assert mac_backend.name == "macos"
    assert mac.MacOSHotkeyBackend is MacOSHotkeyBackend
