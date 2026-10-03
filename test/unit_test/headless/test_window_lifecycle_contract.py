"""Window lifecycle regressions with fake platform APIs; no desktop mutations."""
import ctypes
import sys
from types import SimpleNamespace

import pytest


def test_restore_minimized_macos_window(monkeypatch):
    from je_auto_control.wrapper.window_backends.macos_backend import MacOSWindowBackend
    info = {'number': 42, 'pid': 100, 'bounds': {'X': 10, 'Y': 20}, 'title': 'Hidden'}
    queries, restored = [], []
    def query(options, window_id):
        queries.append((options, window_id))
        return [info] if options == 8 and window_id == 42 else []
    quartz = SimpleNamespace(kCGWindowListOptionOnScreenOnly=1,
                             kCGWindowListExcludeDesktopElements=2,
                             kCGWindowListOptionIncludingWindow=8, kCGNullWindowID=0,
                             kCGWindowNumber='number', kCGWindowOwnerPID='pid',
                             kCGWindowBounds='bounds', kCGWindowName='title',
                             CGWindowListCopyWindowInfo=query)
    monkeypatch.setitem(sys.modules, 'Quartz', quartz)
    monkeypatch.setitem(sys.modules, 'ApplicationServices', SimpleNamespace(
        AXUIElementSetAttributeValue=lambda window, key, value: restored.append((window, key, value)) or 0))
    backend = object.__new__(MacOSWindowBackend)
    monkeypatch.setattr(backend, '_ax_windows_for', lambda pid: ['ax-window'])
    monkeypatch.setattr('je_auto_control.wrapper.window_backends.macos_backend._best_match',
                        lambda *args: 'ax-window')
    backend.restore(42)
    assert restored == [('ax-window', 'AXMinimized', False)]
    assert (8, 42) in queries


def test_foreground_failure_propagates(monkeypatch):
    from je_auto_control.wrapper import auto_control_window as window
    from je_auto_control.utils.exception.exceptions import AutoControlActionException
    from je_auto_control.wrapper.window_backends.base import WindowManageBackend
    class RefusedBackend(WindowManageBackend):
        def is_minimized(self, hwnd):
            return False
        def set_foreground(self, hwnd):
            pass
        def foreground_window(self):
            return 99
    backend = RefusedBackend()
    monkeypatch.setattr(window, 'get_backend', lambda: backend)
    monkeypatch.setattr(window, 'find_window', lambda *args: (42, 'Target'))
    with pytest.raises(AutoControlActionException):
        window.focus_window('Target')


@pytest.mark.parametrize('poll', [30, float('inf'), float('nan')])
def test_poll_is_bounded(monkeypatch, poll):
    from je_auto_control.wrapper import auto_control_window as window
    from je_auto_control.utils.exception.exceptions import AutoControlActionException
    elapsed, sleeps = [0.0], []
    def sleep(delay):
        assert 0 < delay <= 0.1 - elapsed[0] + 1e-9
        sleeps.append(delay)
        elapsed[0] += delay
    monkeypatch.setattr(window, 'find_window', lambda *args: None)
    monkeypatch.setattr(window, 'time', SimpleNamespace(monotonic=lambda: elapsed[0], sleep=sleep))
    with pytest.raises(AutoControlActionException):
        window.wait_for_window('Absent', timeout=0.1, poll=poll)
    assert sum(sleeps) <= 0.1


@pytest.mark.skipif(sys.platform != 'win32', reason='Win32 module uses native ctypes prototypes')
def test_zorder_reports_real_failure(monkeypatch):
    from je_auto_control.windows.window import windows_window_manage as wm
    from je_auto_control.utils.window_zorder import window_zorder as zorder
    monkeypatch.setattr('je_auto_control.wrapper.auto_control_window.find_window', lambda title: (42, title))
    monkeypatch.setattr(wm, '_user32', SimpleNamespace(SetWindowPos=lambda *args: False))
    assert zorder.bring_to_front('Target') is False


@pytest.mark.skipif(sys.platform != 'win32', reason='Win32 module uses native ctypes prototypes')
def test_cloaked_window_filtered(monkeypatch):
    from je_auto_control.windows.window import windows_window_manage as wm
    def enumerate_windows(callback, _argument):
        for hwnd in (1, 2, 3):
            callback(hwnd, 0)
        return True
    def window_text(hwnd, buffer, _size):
        buffer.value = 'Window'
        return 6
    def rect(hwnd, pointer):
        pointer._obj.right = 0 if hwnd == 3 else 100
        pointer._obj.bottom = 100
        return True
    def attribute(hwnd, _key, pointer, _size):
        pointer._obj.value = 1 if hwnd == 2 else 0
        return 0
    monkeypatch.setattr(wm, '_user32', SimpleNamespace(
        EnumWindows=enumerate_windows, IsWindowVisible=lambda hwnd: True,
        GetWindowTextLengthW=lambda hwnd: 6, GetWindowTextW=window_text, GetWindowRect=rect))
    monkeypatch.setattr(ctypes, 'WinDLL', lambda *args, **kwargs:
                        SimpleNamespace(DwmGetWindowAttribute=attribute))
    assert wm.get_all_window_hwnd() == [(1, 'Window')]


@pytest.mark.skipif(sys.platform != 'win32', reason='Win32 module uses native ctypes prototypes')
@pytest.mark.parametrize('character', ['a', ''])
def test_post_key_delivers_each_event_once(monkeypatch, character):
    from je_auto_control.windows.window import windows_window_manage as wm
    messages = []
    monkeypatch.setattr(wm, 'get_focused_control', lambda hwnd: hwnd)
    monkeypatch.setattr(wm, '_user32', SimpleNamespace(
        PostMessageW=lambda *args: messages.append(args) or True,
        MapVirtualKeyW=lambda code, kind: 0x1e))
    assert wm.post_key(42, 65, character)
    assert [msg[1] for msg in messages] == ([wm.WM_CHAR] if character else [wm.WM_KEYDOWN, wm.WM_KEYUP])
    if not character:
        assert messages[0][3] == 1 | (0x1e << 16)
        assert messages[1][3] == 0xC0000001 | (0x1e << 16)


@pytest.mark.skipif(sys.platform != 'win32', reason='Native Win32 boundary')
def test_capture_does_not_move_window(monkeypatch, tmp_path):
    from je_auto_control.utils.window_capture import window_capture as capture
    from je_auto_control.windows.window import windows_window_manage as wm
    state = {'rect': (3, 4, 203, 104), 'show': 3}
    before = dict(state)
    monkeypatch.setattr('je_auto_control.wrapper.auto_control_window.find_window', lambda *a, **k: (42, 'Target'))
    monkeypatch.setattr(capture, '_win32_geometry', lambda hwnd: (10, 11, 186, 93))
    monkeypatch.setattr(wm, 'move_window', lambda *args: state.update(rect=args[1:]) or True)
    outputs = []
    assert capture.capture_window('Target', tmp_path / 'shot.png',
                                  capture=lambda path, rect: outputs.append(rect)) is not None
    assert outputs == [(10, 11, 186, 93)]
    assert state == before


@pytest.mark.skipif(sys.platform != 'win32', reason='Native Win32 boundary')
def test_layout_restores_native_placement_without_border_drift(monkeypatch, tmp_path):
    from je_auto_control.utils.window_capture import window_capture as capture
    from je_auto_control.windows.window import windows_window_manage as wm
    state = {'show': 3, 'rect': (-900, 40, -300, 440), 'flags': 2}
    restored = []
    def get_placement(hwnd, pointer):
        p = pointer._obj
        p.showCmd, p.flags = state['show'], state['flags']
        p.rcNormalPosition.left, p.rcNormalPosition.top = state['rect'][:2]
        p.rcNormalPosition.right, p.rcNormalPosition.bottom = state['rect'][2:]
        p.ptMinPosition.x, p.ptMinPosition.y = -1, -1
        p.ptMaxPosition.x, p.ptMaxPosition.y = -900, 40
        return True
    def set_placement(hwnd, pointer):
        p = pointer._obj
        restored.append((hwnd, p.showCmd, p.flags, p.rcNormalPosition.left, p.rcNormalPosition.top,
                         p.rcNormalPosition.right, p.rcNormalPosition.bottom))
        return True
    def full_rect(hwnd, pointer):
        r = pointer._obj
        r.left, r.top, r.right, r.bottom = -907, 33, -293, 440
        return True
    monkeypatch.setattr(wm, '_user32', SimpleNamespace(
        GetWindowPlacement=get_placement, SetWindowPlacement=set_placement, GetWindowRect=full_rect,
        MoveWindow=lambda *args: restored.append(('drift', args)) or True))
    monkeypatch.setattr(capture, '_win32_geometry', lambda hwnd: (-900, 40, 600, 400))
    monkeypatch.setattr('je_auto_control.wrapper.auto_control_window.list_windows', lambda **k: [(42, 'Target')])
    layout = capture.save_window_layout(tmp_path / 'layout.json')
    assert capture.restore_window_layout(tmp_path / 'layout.json') == 1
    assert restored == [(42, 3, 2, -900, 40, -300, 440)]
    assert layout[0]['x'] == -907


@pytest.mark.skipif(sys.platform != 'win32', reason='Native Win32 boundary')
@pytest.mark.parametrize('operation', ['snap', 'grid', 'cascade'])
def test_layout_uses_work_area_with_offset(monkeypatch, operation):
    from je_auto_control.utils.window_capture import window_capture as capture
    from je_auto_control.windows.window import windows_window_manage as wm
    def work_area(action, param, pointer, flags):
        r = pointer._obj
        r.left, r.top, r.right, r.bottom = 40, 50, 1040, 750
        return True
    monkeypatch.setattr(wm, '_user32', SimpleNamespace(SystemParametersInfoW=work_area))
    monkeypatch.setattr(capture, '_default_screen_size', lambda: (1200, 900))
    moved = []
    def mover(*args):
        moved.append(args)
        return True
    if operation == 'snap':
        assert capture.snap_window('Target', 'max', mover=mover)
    elif operation == 'grid':
        assert capture.arrange_grid(['Target'], mover=mover) == 1
    else:
        assert capture.arrange_cascade(['Target'], mover=mover) == 1
    _, x, y, width, height = moved[0]
    assert (x, y) == (40, 50)
    assert x + width <= 1040 and y + height <= 750


@pytest.mark.skipif(sys.platform != 'win32', reason='Native Win32 boundary')
@pytest.mark.parametrize('prior_visible', [False, True])
def test_show_checks_resulting_state_not_previous_visibility(monkeypatch, prior_visible):
    from je_auto_control.windows.window import windows_window_manage as wm
    visible = [prior_visible]
    def show(hwnd, command):
        visible[0] = True
        return prior_visible
    monkeypatch.setattr(wm, '_user32', SimpleNamespace(
        ShowWindow=show, IsWindow=lambda hwnd: True, IsWindowVisible=lambda hwnd: visible[0],
        IsIconic=lambda hwnd: False, IsZoomed=lambda hwnd: False, SetForegroundWindow=lambda hwnd: True))
    assert wm.show_window(42, 5) is True


@pytest.mark.skipif(sys.platform != 'win32', reason='Native Win32 boundary')
def test_show_refusal_is_visible_to_wrapper(monkeypatch):
    from je_auto_control.windows.window import windows_window_manage as wm
    from je_auto_control.wrapper import auto_control_window as window
    from je_auto_control.utils.exception.exceptions import AutoControlActionException
    monkeypatch.setattr(window, 'find_window', lambda *args: (42, 'Target'))
    monkeypatch.setattr(wm, '_user32', SimpleNamespace(
        ShowWindow=lambda *args: True, IsWindow=lambda hwnd: True, IsWindowVisible=lambda hwnd: False,
        IsIconic=lambda hwnd: False, IsZoomed=lambda hwnd: False, SetForegroundWindow=lambda hwnd: False))
    with pytest.raises(AutoControlActionException):
        window.show_window_by_title('Target')


def test_post_key_aliases_use_the_shared_resolver():
    from je_auto_control.wrapper import auto_control_window as window
    assert window._resolve_key('enter') == window._resolve_key('return')
    assert window._resolve_key('esc') == window._resolve_key('escape')


@pytest.mark.skipif(sys.platform != 'win32', reason='Native Win32 boundary')
def test_restore_show_refuses_a_still_minimized_window(monkeypatch):
    from je_auto_control.windows.window import windows_window_manage as wm
    monkeypatch.setattr(wm, '_user32', SimpleNamespace(
        ShowWindow=lambda *args: True, IsWindow=lambda hwnd: True, IsWindowVisible=lambda hwnd: True,
        IsIconic=lambda hwnd: True, IsZoomed=lambda hwnd: False, SetForegroundWindow=lambda hwnd: False))
    assert wm.show_window(42, 9) is False


@pytest.mark.skipif(sys.platform != 'win32', reason='Native Win32 boundary')
@pytest.mark.parametrize('saved', [{}, {'flags': 0, 'show_cmd': 1, 'min_position': [0],
                                      'max_position': [0, 0], 'normal_position': [0, 0, 100, 100]}])
def test_invalid_native_placement_has_a_framework_error(monkeypatch, saved):
    from je_auto_control.windows.window import windows_window_manage as wm
    from je_auto_control.utils.exception.exceptions import AutoControlActionException
    def reject_native_call(*args):
        raise AssertionError('Invalid placement must not reach the desktop')
    monkeypatch.setattr(wm, '_user32', SimpleNamespace(SetWindowPlacement=reject_native_call))
    with pytest.raises(AutoControlActionException):
        wm.set_window_placement(42, saved)
