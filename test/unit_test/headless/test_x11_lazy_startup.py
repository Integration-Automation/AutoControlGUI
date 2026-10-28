"""Verify X11 acquisition and recording admission with fake desktop boundaries."""
import importlib
import importlib.util
import os
from pathlib import Path
from queue import Queue
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor
from threading import Event
from types import ModuleType, SimpleNamespace

import pytest

import je_auto_control
from je_auto_control.utils.exception.exceptions import AutoControlException


@pytest.fixture
def x11(monkeypatch):
    monkeypatch.setattr(sys, "platform", "linux")
    calls = []

    def refuse(*args, **kwargs):
        raise AssertionError("unexpected desktop acquisition")

    modules = {}
    for name in ("Xlib", "Xlib.display", "Xlib.ext", "Xlib.ext.xtest", "Xlib.ext.record", "Xlib.protocol"):
        module = ModuleType(name)
        modules[name] = module
        monkeypatch.setitem(sys.modules, name, module)
    modules["Xlib.display"].Display = refuse
    modules["Xlib"].X = SimpleNamespace(KeyPress=2, KeyRelease=3, ButtonPress=4, ButtonRelease=5,
                                       MotionNotify=6, KeyReleaseMask=2, ButtonReleaseMask=8, ZPixmap=2)
    modules["Xlib"].XK = SimpleNamespace(string_to_keysym=lambda name: name)
    modules["Xlib"].protocol = modules["Xlib.protocol"]
    modules["Xlib.ext"].record = modules["Xlib.ext.record"]
    modules["Xlib.ext.record"].AllClients = 3
    modules["Xlib.ext.xtest"].fake_input = lambda *args, **kwargs: calls.append(args[1:])
    modules["Xlib.protocol"].rq = SimpleNamespace()

    def load(suffix):
        name = "je_auto_control." + suffix
        path = Path(je_auto_control.__file__).parent.joinpath(*suffix.split(".")).with_suffix(".py")
        spec = importlib.util.spec_from_file_location(name, path)
        module = importlib.util.module_from_spec(spec)
        monkeypatch.setitem(sys.modules, name, module)
        spec.loader.exec_module(module)
        parent, attribute = name.rsplit(".", 1)
        monkeypatch.setattr(importlib.import_module(parent), attribute, module, raising=False)
        return module

    display = load("linux_with_x11.core.utils.x11_linux_display")
    vk = load("linux_with_x11.core.utils.x11_linux_vk")
    keyboard = load("linux_with_x11.keyboard.x11_linux_keyboard_control")
    mouse = load("linux_with_x11.mouse.x11_linux_mouse_control")
    screen = load("linux_with_x11.screen.x11_linux_screen")
    listener = load("linux_with_x11.listener.x11_linux_listener")
    recorder = load("linux_with_x11.record.x11_linux_record")
    assembly = load("wrapper._platform_linux")
    return SimpleNamespace(display=display, vk=vk, keyboard=keyboard, mouse=mouse, screen=screen,
                           listener=listener, recorder=recorder, assembly=assembly, load=load, calls=calls)


def test_import_and_stop_before_start_acquire_nothing(x11):
    assert x11.display._DISPLAY is None
    assert x11.vk._TABLE is None
    assert x11.listener._LISTENER is None
    assert x11.assembly._INPUT_PAIR is None
    assert x11.recorder.x11_linux_recorder.stop_record().empty()
    for module in (x11.vk, x11.assembly):
        with pytest.raises(AttributeError):
            getattr(module, "unrelated_attribute")


def test_shared_display_failure_retry_and_concurrent_first_use(x11, monkeypatch):
    failure = OSError("display absent")
    attempts = []
    connection = object()

    def acquire(name):
        attempts.append(name)
        if len(attempts) == 1:
            raise failure
        return connection

    monkeypatch.setattr(x11.display, "Display", acquire)
    with pytest.raises(AutoControlException) as caught:
        x11.display.get_display()
    assert caught.value.__cause__ is failure
    with ThreadPoolExecutor(max_workers=8) as pool:
        results = list(pool.map(lambda _: x11.display.get_display(), range(32)))
    assert all(result is connection for result in results)
    assert len(attempts) == 2


def test_key_table_is_complete_real_shared_dict_and_retryable(x11, monkeypatch):
    conversions = []

    def keycode(symbol):
        conversions.append(symbol)
        if len(conversions) == 3:
            raise OSError("keymap failed")
        return {"Help": 0, "a": 38, "A": 38, "Return": 36, "Escape": 9,
                "BackSpace": 22, "backslash": 51}.get(symbol, 100)

    monkeypatch.setattr(x11.display, "Display", lambda _: SimpleNamespace(keysym_to_keycode=keycode))
    with pytest.raises(OSError, match="keymap failed"):
        x11.vk.get_keyboard_keys_table()
    assert x11.vk._TABLE is None
    with ThreadPoolExecutor(max_workers=8) as pool:
        tables = list(pool.map(lambda _: x11.assembly.keyboard_keys_table, range(16)))
    table = tables[0]
    assert type(table) is dict
    assert all(value is table for value in tables)
    assert len(table) == 181
    assert all(type(code) is int for code in table.values())
    assert table["help"] == 0
    assert {"a", "A", "\n", "\r", "\t", "\b", "pgup", "pageup", "esc", "enter", "return"} <= table.keys()
    assert table["enter"] == table["return"] == x11.vk.x11_linux_key_enter
    assert table["a"] == table["A"] == 38
    assert table["\n"] == table["\r"] == table["enter"] == 36
    assert table["\b"] == table["\\"] == 51
    assert table["backspace"] == 22
    assert x11.vk.x11_linux_key_escape == table["esc"]
    assert x11.vk.x11_linux_key_printscreen == table["prtsc"]
    table["custom"] = 42
    assert x11.assembly.get_keyboard_keys_table()["custom"] == 42


def test_public_table_access_and_wrapper_replacement(x11, monkeypatch):
    monkeypatch.setenv("JE_AUTOCONTROL_LINUX_DISPLAY_SERVER", "x11")
    monkeypatch.setattr(x11.display, "Display", lambda _: SimpleNamespace(keysym_to_keycode=lambda _: 38))
    platform = x11.load("wrapper.platform_wrapper")
    keyboard = x11.load("wrapper.auto_control_keyboard")
    assert x11.display._DISPLAY is None
    table = platform.keyboard_keys_table
    assert table is keyboard.keyboard_keys_table is keyboard.get_keyboard_keys_table()
    monkeypatch.setattr(je_auto_control, "get_keyboard_keys_table", keyboard.get_keyboard_keys_table)
    assert je_auto_control.keyboard_keys_table is table
    replacement = {"a": 51}
    monkeypatch.setattr(keyboard, "keyboard_keys_table", replacement)
    assert keyboard.get_keyboard_keys_table() is replacement
    assert keyboard._resolve_keycode("a") == 51


def test_legacy_constants_are_discoverable_and_wildcard_import_resolves_integers(x11, monkeypatch):
    names = {name for name in dir(x11.vk) if name.startswith("x11_linux_key_")}
    assert len(names) == 183
    assert names | {"get_keyboard_keys_table"} == set(x11.vk.__all__)
    assert x11.display._DISPLAY is None
    codes = {"a": 38, "A": 38, "Return": 36, "Escape": 9, "Print": 107}
    monkeypatch.setattr(x11.display, "Display", lambda _: SimpleNamespace(
        keysym_to_keycode=lambda symbol: codes.get(symbol, 100)))
    imported = {}
    exec("from je_auto_control.linux_with_x11.core.utils.x11_linux_vk import *", imported)
    assert {name for name in imported if name != "__builtins__"} == set(x11.vk.__all__)
    assert all(type(imported[name]) is int for name in names)
    assert imported["x11_linux_key_a"] == imported["x11_linux_key_A"] == 38
    assert imported["x11_linux_key_enter"] == imported["x11_linux_key_return"] == 36
    assert imported["x11_linux_key_escape"] == imported["x11_linux_key_esc"] == 9
    assert imported["x11_linux_key_printscreen"] == imported["x11_linux_key_prtsc"] == 107
    assert imported["get_keyboard_keys_table"]() is x11.vk.get_keyboard_keys_table()


def test_screen_and_input_do_not_start_listener(x11, monkeypatch):
    connection = SimpleNamespace(screen=lambda: SimpleNamespace(width_in_pixels=123, height_in_pixels=456),
                                 sync=lambda: None)
    monkeypatch.setattr(x11.display, "Display", lambda _: connection)
    assert x11.assembly.screen.size() == (123, 456)
    assert x11.assembly._INPUT_PAIR is None
    x11.assembly.keyboard.press_key(38)
    x11.assembly.mouse.press_mouse(1)
    assert x11.calls == [(2, 38), (4, 1)]
    assert x11.listener._LISTENER is None


def test_invalid_key_does_not_select_input_or_acquire_display(x11):
    for operation in (x11.keyboard.press_key, x11.keyboard.release_key, x11.assembly.keyboard.press_key):
        with pytest.raises(AutoControlException, match="not bound"):
            operation(0)
    assert x11.display._DISPLAY is None
    assert x11.assembly._INPUT_PAIR is None


@pytest.mark.parametrize("platform_name", ["freebsd14", "openbsd7", "netbsd10"])
def test_bsd_assembly_keeps_the_lazy_x11_path(x11, monkeypatch, platform_name):
    monkeypatch.setattr(sys, "platform", platform_name)
    platform = x11.load("wrapper.platform_wrapper")
    assert platform.screen is x11.screen
    assert platform.keyboard is x11.assembly.keyboard
    assert x11.display._DISPLAY is None
    assert x11.listener._LISTENER is None


def test_input_backend_selection_is_shared_and_retryable(x11, monkeypatch):
    chosen = []
    operations = []
    keyboard = SimpleNamespace(press_key=lambda code: operations.append(("key", code)))
    mouse = SimpleNamespace(position=lambda: (1, 2))

    def select():
        chosen.append(True)
        if len(chosen) == 1:
            raise OSError("temporary selection failure")
        return keyboard, mouse

    monkeypatch.setattr(x11.assembly, "_select_input_backend", select)
    with pytest.raises(OSError):
        x11.assembly.keyboard.press_key(38)
    x11.assembly.keyboard.press_key(38)
    assert x11.assembly.mouse.position() == (1, 2)
    assert chosen == [True, True]
    assert operations == [("key", 38)]
    assert x11.display._DISPLAY is None


@pytest.mark.parametrize("available", [False, True])
def test_uinput_probe_is_deferred_and_fallback_preserved(x11, monkeypatch, available):
    monkeypatch.setenv("JE_AUTOCONTROL_LINUX_BACKEND", "uinput")
    probes = []
    fake = ModuleType("je_auto_control.linux_with_x11.uinput")
    fake.keyboard = SimpleNamespace(press_key=lambda _: None)
    fake.mouse = SimpleNamespace(position=lambda: (2, 3))
    fake.is_available = lambda: probes.append(True) or available
    monkeypatch.setitem(sys.modules, fake.__name__, fake)
    assert probes == []
    pair = x11.assembly._get_input_backend()
    assert pair == ((fake.keyboard, fake.mouse) if available else (x11.keyboard, x11.mouse))
    assert x11.assembly._get_input_backend() is pair
    assert probes == [True]


class _RecordDisplay:
    def __init__(self):
        self.calls = []
        self.display = object()

    def record_create_context(self, *args):
        self.calls.append("create")
        return 7

    def record_enable_context(self, context, callback):
        self.calls.append("enable")

    def record_free_context(self, context):
        self.calls.append("free")

    def close(self):
        self.calls.append("close")


def test_listener_queue_precedes_start_and_finalization_closes(x11, monkeypatch):
    connection = _RecordDisplay()
    monkeypatch.setattr(x11.listener, "Display", lambda: connection)
    queue = Queue()

    def start(listener):
        assert listener.handler.record_queue is queue
        assert listener.handler.record_flag
        connection.calls.append("start")

    monkeypatch.setattr(x11.listener.XWindowsKeypressListener, "start", start)
    x11.listener.x11_linux_record(queue)
    listener = x11.listener._LISTENER
    listener.run()
    assert connection.calls == ["create", "start", "enable", "free", "close"]
    assert listener.closed.is_set()
    assert x11.display._DISPLAY is None
    assert x11.assembly._INPUT_PAIR is None


@pytest.mark.parametrize("failure_step", ["create", "start", "enable"])
def test_listener_failure_releases_owned_resources(x11, monkeypatch, failure_step):
    connection = _RecordDisplay()
    monkeypatch.setattr(x11.listener, "Display", lambda: connection)

    def fail(*args):
        raise OSError(failure_step)

    monkeypatch.setattr(x11.listener.XWindowsKeypressListener, "start", lambda _: None)
    if failure_step == "start":
        monkeypatch.setattr(x11.listener.XWindowsKeypressListener, "start", fail)
    else:
        monkeypatch.setattr(connection, "record_" + failure_step + "_context", fail)
    with pytest.raises(AutoControlException) as caught:
        x11.listener.check_key_is_press(38)
        x11.listener._LISTENER.run()
    assert isinstance(caught.value.__cause__, OSError)
    assert connection.calls[-1] == "close"
    assert ("free" in connection.calls) == (failure_step != "create")
    replacement = _RecordDisplay()
    monkeypatch.setattr(x11.listener, "Display", lambda: replacement)
    monkeypatch.setattr(x11.listener.XWindowsKeypressListener, "start", lambda _: None)
    assert x11.listener.check_key_is_press(38) is False
    assert replacement.calls == ["create"]


def test_listener_uncertain_close_blocks_replacement_and_preserves_cause(x11, monkeypatch):
    connection = _RecordDisplay()
    acquisitions = []
    startup_error = OSError("context creation failed")

    def acquire():
        acquisitions.append(True)
        return connection

    def fail_create(*args):
        raise startup_error

    def fail_close():
        raise OSError("close failed")

    monkeypatch.setattr(x11.listener, "Display", acquire)
    monkeypatch.setattr(connection, "record_create_context", fail_create)
    monkeypatch.setattr(connection, "close", fail_close)
    with pytest.raises(AutoControlException) as caught:
        x11.listener.check_key_is_press(38)
    assert caught.value.__cause__ is startup_error
    assert str(x11.listener._LISTENER.failure) == "close failed"
    assert not x11.listener._LISTENER.closed.is_set()
    with pytest.raises(AutoControlException, match="cleanup is incomplete"):
        x11.listener.check_key_is_press(38)
    assert acquisitions == [True]


def test_listener_closes_connection_even_when_context_free_fails(x11, monkeypatch):
    connection = _RecordDisplay()
    monkeypatch.setattr(x11.listener, "Display", lambda: connection)
    monkeypatch.setattr(x11.listener.XWindowsKeypressListener, "start", lambda _: None)
    x11.listener.check_key_is_press(38)

    def fail_free(context):
        raise OSError("free failed")

    monkeypatch.setattr(connection, "record_free_context", fail_free)
    with pytest.raises(AutoControlException, match="free failed"):
        x11.listener._LISTENER.run()
    assert connection.calls[-1] == "close"
    assert x11.listener._LISTENER.closed.is_set()


def test_concurrent_listener_first_use_and_cleanup_do_not_overlap_owners(x11, monkeypatch):
    connection = _RecordDisplay()
    acquisitions = []
    closing, finish_close = Event(), Event()

    def acquire():
        acquisitions.append(True)
        return connection

    def close():
        closing.set()
        if not finish_close.wait(3):
            raise RuntimeError("test did not release cleanup")

    monkeypatch.setattr(x11.listener, "Display", acquire)
    monkeypatch.setattr(connection, "close", close)
    monkeypatch.setattr(x11.listener.XWindowsKeypressListener, "start", lambda _: None)
    with ThreadPoolExecutor(max_workers=8) as pool:
        assert list(pool.map(x11.listener.check_key_is_press, [38] * 16)) == [False] * 16
        owner = x11.listener._LISTENER
        cleanup = pool.submit(owner.close)
        try:
            assert closing.wait(3)
            assert x11.listener.check_key_is_press(38) is False
            assert x11.listener._LISTENER is owner
            assert acquisitions == [True]
        finally:
            finish_close.set()
        cleanup.result(timeout=3)
    assert owner.closed.is_set()


def test_recording_refuses_retiring_owner_then_uses_new_owner_after_close(x11, monkeypatch):
    connection = _RecordDisplay()
    replacement = _RecordDisplay()
    displays = iter((connection, replacement))
    closing, finish_close = Event(), Event()

    def close():
        closing.set()
        if not finish_close.wait(3):
            raise RuntimeError("test did not release cleanup")

    monkeypatch.setattr(x11.listener, "Display", lambda: next(displays))
    monkeypatch.setattr(connection, "close", close)
    monkeypatch.setattr(x11.listener.XWindowsKeypressListener, "start", lambda _: None)
    initial_queue, rejected_queue, next_queue = Queue(), Queue(), Queue()
    x11.listener.x11_linux_record(initial_queue)
    owner = x11.listener._LISTENER
    with ThreadPoolExecutor(max_workers=1) as pool:
        cleanup = pool.submit(owner.close)
        try:
            assert closing.wait(3)
            with pytest.raises(AutoControlException, match="retiring"):
                x11.listener.x11_linux_record(rejected_queue)
            assert owner.handler.record_queue is initial_queue
        finally:
            finish_close.set()
        cleanup.result(timeout=3)
    x11.listener.x11_linux_record(next_queue)
    assert x11.listener._LISTENER is not owner
    assert x11.listener._LISTENER.handler.record_queue is next_queue
    assert replacement.calls == ["create"]


@pytest.mark.skipif(not sys.platform.startswith("linux"), reason="actual Linux package import")
@pytest.mark.parametrize("backend", ["x11", "uinput"])
def test_actual_package_import_has_no_desktop_contact(backend):
    script = '''
import sys, threading
events = []
def audit(event, args):
    if event == "socket.connect" or (event == "open" and isinstance(args[0], str)
                                     and args[0].startswith("/dev/uinput")):
        events.append(event)
        raise RuntimeError(event)
def refuse_start(*args, **kwargs):
    events.append("Thread.start")
    raise RuntimeError("Thread.start")
threading.Thread.start = refuse_start
sys.addaudithook(audit)
import je_auto_control as ac
assert callable(ac.get_keyboard_keys_table)
assert callable(ac.screen_size)
assert "keyboard_keys_table" in ac.__all__
assert not events, events
'''
    env = {key: value for key, value in os.environ.items()
           if key not in {"DISPLAY", "WAYLAND_DISPLAY", "XDG_SESSION_TYPE", "DBUS_SESSION_BUS_ADDRESS"}}
    env.update(JE_AUTOCONTROL_LINUX_BACKEND=backend, JE_AUTOCONTROL_LINUX_DISPLAY_SERVER="x11")
    result = subprocess.run([sys.executable, "-c", script], env=env, capture_output=True, text=True, timeout=60)
    assert result.returncode == 0, result.stdout + result.stderr
