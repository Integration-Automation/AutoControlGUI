"""Input correctness and confidential typing with fake native sinks."""
import logging
import sys
from types import SimpleNamespace

import pytest


@pytest.fixture
def keys(monkeypatch):
    from je_auto_control.wrapper import auto_control_keyboard as keyboard
    events, output, held, records = [], [], set(), []
    table = {'shift': 16, 'shift_l': 16, 'return': 13, 'tab': 9,
             'H': 72, 'h': 72, 'i': 73, 'a': 65, 'A': 65, 'b': 66}
    def press(key):
        events.append(('down', key))
        held.add(key)
    def release(key):
        events.append(('up', key))
        if key in held:
            if key in (13, 9):
                output.append('\n' if key == 13 else '\t')
            elif 65 <= key <= 90:
                output.append(chr(key) if 16 in held else chr(key).lower())
        held.discard(key)
    def unicode(unit):
        events.append(('unicode', unit))
        output.append(chr(unit))
    backend = SimpleNamespace(press_key=press, release_key=release, type_unicode_unit=unicode)
    monkeypatch.setattr(keyboard, 'keyboard', backend)
    monkeypatch.setattr(keyboard, 'keyboard_keys_table', table)
    monkeypatch.setattr(keyboard, 'sys', SimpleNamespace(platform='win32'))
    monkeypatch.setattr(keyboard, 'is_windows', lambda: True)
    monkeypatch.setattr(keyboard, 'is_x11_unix', lambda: False)
    monkeypatch.setattr(keyboard, 'record_action_to_list', lambda *args: records.append(args))
    return SimpleNamespace(module=keyboard, backend=backend, events=events, output=output,
                           held=held, records=records)


def test_case_and_shift_preserved(keys):
    assert keys.module.write('Hi') == 'Hi'
    assert ''.join(keys.output) == 'Hi'
    keys.output.clear()
    keys.module.type_keyboard('a', is_shift=True)
    assert ''.join(keys.output) == 'A'
    assert keys.held == set()


def test_shift_released_on_typing_failure(keys):
    from je_auto_control.utils.exception.exceptions import AutoControlKeyboardException
    def fail(key):
        if key == 65:
            raise OSError('native keyboard refusal')
        keys.events.append(('down', key))
        keys.held.add(key)
    keys.backend.press_key = fail
    with pytest.raises(AutoControlKeyboardException):
        keys.module.type_keyboard('a', is_shift=True)
    assert ('up', 16) in keys.events
    assert keys.held == set()


def test_crlf_sends_single_enter(keys):
    keys.module.write('a\r\nb')
    assert ''.join(keys.output) == 'a\nb'
    assert keys.events.count(('down', 13)) == 1


@pytest.mark.parametrize('secret', ['Hi-confidential-519', 'Hi\tconfidential'])
def test_write_secret_leaves_no_text(keys, caplog, secret):
    with caplog.at_level(logging.INFO, logger='AutoControlGUI'):
        result = keys.module.write(secret, secret=True)
    assert ''.join(keys.output) == secret
    assert result is None
    assert keys.records == []
    assert secret not in caplog.text
    assert caplog.records == []


def test_secret_failure_does_not_echo_backend_text(keys, caplog):
    from je_auto_control.utils.exception.exceptions import AutoControlKeyboardException
    secret = 'never-log-this'
    def fail(unit):
        raise RuntimeError(secret)
    keys.backend.type_unicode_unit = fail
    with caplog.at_level(logging.INFO, logger='AutoControlGUI'):
        with pytest.raises(AutoControlKeyboardException) as error:
            keys.module.write(secret, secret=True)
    assert secret not in str(error.value)
    assert secret not in caplog.text
    assert keys.records == []


def test_executor_secret_callback_and_result_are_redacted(keys, caplog):
    from je_auto_control.utils.executor.action_executor import Executor
    secret = 'Hi-confidential'
    callbacks = []
    executor = Executor()
    executor.event_dict['AC_write'] = keys.module.write
    action = ['AC_write', {'write_string': secret, 'secret': True}]
    with caplog.at_level(logging.INFO, logger='AutoControlGUI'):
        result = executor.execute_action([action], step_callback=callbacks.append)
    assert ''.join(keys.output) == secret
    assert secret not in repr(result) + repr(callbacks) + caplog.text
    assert action == ['AC_write', {'write_string': secret, 'secret': True}]


@pytest.mark.parametrize('invalid', [float('nan'), float('inf'), -float('inf')])
def test_nan_does_not_move_mouse(monkeypatch, invalid):
    from je_auto_control.wrapper import auto_control_mouse as mouse
    from je_auto_control.utils.exception.exceptions import AutoControlMouseException
    moved = []
    monkeypatch.setattr(mouse, 'mouse', SimpleNamespace(scroll=lambda *args: moved.append(('scroll', args))))
    monkeypatch.setattr(mouse, '_scroll_bounds', lambda: (-1920, 0, 3840, 1080))
    monkeypatch.setattr(mouse, 'set_mouse_position', lambda *args: moved.append(args))
    with pytest.raises(AutoControlMouseException):
        mouse.mouse_scroll(1, x=invalid, y=100)
    assert moved == []


def test_x11_text_preserves_case_without_unicode(keys, monkeypatch):
    monkeypatch.setattr(keys.module, 'sys', SimpleNamespace(platform='linux'))
    monkeypatch.setattr(keys.module, 'is_windows', lambda: False)
    monkeypatch.setattr(keys.module, 'is_x11_unix', lambda: True)
    del keys.backend.type_unicode_unit
    assert keys.module.write('Hi') == 'Hi'
    assert ''.join(keys.output) == 'Hi'
    assert keys.held == set()


def test_control_backspace_accepts_platform_key_name(keys, monkeypatch):
    monkeypatch.setitem(keys.module.keyboard_keys_table, 'backspace', 8)
    keys.module.write('\b')
    assert ('down', 8) in keys.events
    assert ('up', 8) in keys.events


def test_scroll_direction_and_rounding(monkeypatch):
    from je_auto_control.wrapper import auto_control_mouse as mouse
    seen = []
    monkeypatch.setattr(mouse, 'mouse', SimpleNamespace(
        scroll=lambda *args: seen.append(args), position=lambda *args: seen.append(args)))
    monkeypatch.setattr(mouse, 'sys', SimpleNamespace(platform='linux'))
    monkeypatch.setattr(mouse, 'is_x11_unix', lambda: True)
    monkeypatch.setattr(mouse, 'is_windows', lambda: False)
    monkeypatch.setattr(mouse, 'logical_virtual_rect', lambda: (-1920, 0, 3840, 1080))
    monkeypatch.setattr(mouse, 'special_mouse_keys_table', {'scroll_up': 4, 'scroll_down': 5})
    mouse.mouse_scroll(1)
    assert seen == [(1, 4)]
    assert mouse._coordinate(-0.6, 'x') == -1
    assert mouse._coordinate(10.9, 'y') == 11


def test_unicode_whitespace_uses_control_keys():
    from je_auto_control.utils.text_unicode.text_unicode import plan_unicode_keys
    assert plan_unicode_keys('a\r\nb\tc') == [
        {'op': 'unicode_unit', 'unit': 97}, {'op': 'key', 'key': 'return'},
        {'op': 'unicode_unit', 'unit': 98}, {'op': 'key', 'key': 'tab'},
        {'op': 'unicode_unit', 'unit': 99}]


def test_dead_key_and_oem_layout():
    from je_auto_control.utils.keyboard_layout import keyboard_layout as layout
    def translate(vk, shifted):
        if vk == 0x36:
            return '' if shifted else '6'
        if vk == 0xe2:
            return '>' if shifted else '<'
        return ''
    table = layout._build_table(translate)
    assert table[0x36] == ('6', None)
    assert table[0xe2] == ('<', '>')


def test_clipboard_missing_name_is_consistent():
    from je_auto_control.utils.clipboard_formats.clipboard_formats import _coerce
    assert _coerce((13, None)) == _coerce({'id': 13, 'name': None}) == (13, '')


def test_layout_translator_does_not_mutate_shared_user32(monkeypatch):
    import ctypes
    from je_auto_control.utils.keyboard_layout import keyboard_layout as layout
    def translate(vk, scan, state, buffer, size, flags, hkl):
        buffer.value = 'a' if vk == 65 else ''
        return len(buffer.value)
    def shared_translate(*args):
        return translate(*args)
    shared_translate.argtypes = ['shared-prototype']
    def map_key(*args):
        return 0
    private = SimpleNamespace(ToUnicodeEx=translate, MapVirtualKeyExW=map_key)
    shared = SimpleNamespace(ToUnicodeEx=shared_translate, MapVirtualKeyExW=map_key)
    monkeypatch.setattr(ctypes, 'WinDLL', lambda *a, **k: private, raising=False)
    monkeypatch.setattr(ctypes, 'windll', SimpleNamespace(user32=shared), raising=False)
    monkeypatch.setattr(layout, '_LAYOUT_CACHE', {})
    monkeypatch.setattr(layout, 'sys', SimpleNamespace(platform='win32'))
    assert layout.layout_char_table(0x407)[65][0] == 'a'
    assert shared_translate.argtypes == ['shared-prototype']


def test_secret_command_accepts_webrunner_parameter_contract(keys, caplog):
    from je_auto_control.utils.executor.action_executor import Executor
    secret = 'Hi-confidential'
    executor = Executor()
    with caplog.at_level(logging.INFO, logger='AutoControlGUI'):
        result = executor.execute_action([['AC_write_secret', {'secret': secret}]], raise_on_error=True)
    assert ''.join(keys.output) == secret
    assert secret not in repr(result) + caplog.text + repr(keys.records)


def test_positional_secret_action_is_redacted_during_dry_run(caplog):
    from je_auto_control.utils.executor.action_executor import Executor
    secret = 'not-for-observers'
    callbacks = []
    with caplog.at_level(logging.INFO, logger='AutoControlGUI'):
        result = Executor().execute_action([['AC_write', [secret, False, True]]],
                                           dry_run=True, step_callback=callbacks.append)
    assert secret not in repr(result) + repr(callbacks) + caplog.text


@pytest.mark.skipif(sys.platform != 'win32', reason='Windows-only key table')
def test_windows_oem_shortcut_names():
    from je_auto_control.wrapper._platform_windows import keyboard_keys_table
    assert {name: keyboard_keys_table.get(name) for name in ('plus', 'minus', 'comma', 'period', 'slash')} == {
        'plus': 0xbb, 'minus': 0xbd, 'comma': 0xbc, 'period': 0xbe, 'slash': 0xbf}


def test_mcp_secret_tool_types_without_audit_or_response_text(keys, tmp_path):
    from je_auto_control.utils.mcp_server.tools import build_default_tool_registry
    from je_auto_control.utils.mcp_server.audit import AuditLogger
    secret = 'Hi-confidential'
    tool = next(tool for tool in build_default_tool_registry() if tool.name == 'ac_write_secret')
    assert tool.invoke({'secret': secret}) is None
    path = tmp_path / 'audit.jsonl'
    AuditLogger(str(path)).record(tool=tool.name, arguments={'secret': secret},
                                status='ok', duration_seconds=0)
    assert ''.join(keys.output) == secret
    assert secret not in path.read_text(encoding='utf-8')


def test_script_builder_secret_input_is_hidden():
    widgets = pytest.importorskip('PySide6.QtWidgets', exc_type=ImportError)
    from je_auto_control.gui.script_builder.step_form_view import StepFormView
    from je_auto_control.gui.script_builder.step_model import action_to_step, step_to_action
    app = widgets.QApplication.instance() or widgets.QApplication([])
    action = ['AC_write_secret', {'secret': '${secrets.LOGIN}', 'is_shift': False}]
    step = action_to_step(action)
    view = StepFormView()
    view.load_step(step)
    editor = view._editors['secret']
    assert editor.echoMode() == widgets.QLineEdit.EchoMode.Password
    assert step_to_action(step) == action
    view.close()
    assert app is not None


def test_public_facade_exports_secret_input():
    import je_auto_control
    assert 'write_secret' in je_auto_control.__all__
