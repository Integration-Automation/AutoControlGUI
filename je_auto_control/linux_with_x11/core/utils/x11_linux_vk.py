"""Resolve X11 key symbols on explicit table or legacy constant access."""
from threading import Lock
from typing import NamedTuple
from Xlib import XK
from je_auto_control.linux_with_x11.core.utils.x11_linux_display import get_display

class _KeySymbol(NamedTuple):
    suffix: str
    symbol: str
    public_name: str | None


_KEY_SYMBOLS = (
    _KeySymbol('backspace', 'BackSpace', 'backspace'),
    _KeySymbol('slash_b', 'backslash', '\x08'),
    _KeySymbol('tab', 'Tab', 'tab'),
    _KeySymbol('enter', 'Return', 'enter'),
    _KeySymbol('return', 'Return', 'return'),
    _KeySymbol('shift', 'Shift_L', 'shift'),
    _KeySymbol('ctrl', 'Control_L', 'ctrl'),
    _KeySymbol('alt', 'Alt_L', 'alt'),
    _KeySymbol('pause', 'Pause', 'pause'),
    _KeySymbol('capslock', 'Caps_Lock', 'capslock'),
    _KeySymbol('esc', 'Escape', 'esc'),
    _KeySymbol('escape', 'Escape', None),
    _KeySymbol('pgup', 'Page_Up', 'pgup'),
    _KeySymbol('pgdn', 'Page_Down', 'pgdn'),
    _KeySymbol('pageup', 'Page_Up', 'pageup'),
    _KeySymbol('pagedown', 'Page_Down', 'pagedown'),
    _KeySymbol('end', 'End', 'end'),
    _KeySymbol('home', 'Home', 'home'),
    _KeySymbol('left', 'Left', 'left'),
    _KeySymbol('up', 'Up', 'up'),
    _KeySymbol('right', 'Right', 'right'),
    _KeySymbol('down', 'Down', 'down'),
    _KeySymbol('select', 'Select', 'select'),
    _KeySymbol('print', 'Print', 'print'),
    _KeySymbol('execute', 'Execute', 'execute'),
    _KeySymbol('prtsc', 'Print', 'prtsc'),
    _KeySymbol('prtscr', 'Print', 'prtscr'),
    _KeySymbol('prntscrn', 'Print', 'prntscrn'),
    _KeySymbol('printscreen', 'Print', None),
    _KeySymbol('insert', 'Insert', 'insert'),
    _KeySymbol('del', 'Delete', 'del'),
    _KeySymbol('delete', 'Delete', 'delete'),
    _KeySymbol('help', 'Help', 'help'),
    _KeySymbol('win', 'Super_L', 'win'),
    _KeySymbol('winleft', 'Super_L', 'winleft'),
    _KeySymbol('winright', 'Super_R', 'winright'),
    _KeySymbol('apps', 'Menu', 'apps'),
    _KeySymbol('num0', 'KP_0', 'num0'),
    _KeySymbol('num1', 'KP_1', 'num1'),
    _KeySymbol('num2', 'KP_2', 'num2'),
    _KeySymbol('num3', 'KP_3', 'num3'),
    _KeySymbol('num4', 'KP_4', 'num4'),
    _KeySymbol('num5', 'KP_5', 'num5'),
    _KeySymbol('num6', 'KP_6', 'num6'),
    _KeySymbol('num7', 'KP_7', 'num7'),
    _KeySymbol('num8', 'KP_8', 'num8'),
    _KeySymbol('num9', 'KP_9', 'num9'),
    _KeySymbol('multiply', 'KP_Multiply', 'multiply'),
    _KeySymbol('add', 'KP_Add', 'add'),
    _KeySymbol('separator', 'KP_Separator', 'separator'),
    _KeySymbol('subtract', 'KP_Subtract', 'subtract'),
    _KeySymbol('decimal', 'KP_Decimal', 'decimal'),
    _KeySymbol('divide', 'KP_Divide', 'divide'),
    _KeySymbol('f1', 'F1', 'f1'),
    _KeySymbol('f2', 'F2', 'f2'),
    _KeySymbol('f3', 'F3', 'f3'),
    _KeySymbol('f4', 'F4', 'f4'),
    _KeySymbol('f5', 'F5', 'f5'),
    _KeySymbol('f6', 'F6', 'f6'),
    _KeySymbol('f7', 'F7', 'f7'),
    _KeySymbol('f8', 'F8', 'f8'),
    _KeySymbol('f9', 'F9', 'f9'),
    _KeySymbol('f10', 'F10', 'f10'),
    _KeySymbol('f11', 'F11', 'f11'),
    _KeySymbol('f12', 'F12', 'f12'),
    _KeySymbol('f13', 'F13', 'f13'),
    _KeySymbol('f14', 'F14', 'f14'),
    _KeySymbol('f15', 'F15', 'f15'),
    _KeySymbol('f16', 'F16', 'f16'),
    _KeySymbol('f17', 'F17', 'f17'),
    _KeySymbol('f18', 'F18', 'f18'),
    _KeySymbol('f19', 'F19', 'f19'),
    _KeySymbol('f20', 'F20', 'f20'),
    _KeySymbol('f21', 'F21', 'f21'),
    _KeySymbol('f22', 'F22', 'f22'),
    _KeySymbol('f23', 'F23', 'f23'),
    _KeySymbol('f24', 'F24', 'f24'),
    _KeySymbol('numlock', 'Num_Lock', 'numlock'),
    _KeySymbol('scrolllock', 'Scroll_Lock', 'scrolllock'),
    _KeySymbol('shiftleft', 'Shift_L', 'shiftleft'),
    _KeySymbol('shiftright', 'Shift_R', 'shiftright'),
    _KeySymbol('ctrlleft', 'Control_L', 'ctrlleft'),
    _KeySymbol('ctrlright', 'Control_R', 'ctrlright'),
    _KeySymbol('altleft', 'Alt_L', 'altleft'),
    _KeySymbol('altright', 'Alt_R', 'altright'),
    _KeySymbol('space', 'space', 'space'),
    _KeySymbol('newline_n', 'Return', '\n'),
    _KeySymbol('newline_r', 'Return', '\r'),
    _KeySymbol('newline_t', 'Tab', '\t'),
    _KeySymbol('exclam', 'exclam', '!'),
    _KeySymbol('numbersign', 'numbersign', '#'),
    _KeySymbol('percent', 'percent', '%'),
    _KeySymbol('dollar', 'dollar', '$'),
    _KeySymbol('ampersand', 'ampersand', '&'),
    _KeySymbol('quotedbl', 'quotedbl', '"'),
    _KeySymbol('apostrophe', 'apostrophe', "'"),
    _KeySymbol('parenleft', 'parenleft', '('),
    _KeySymbol('parenright', 'parenright', ')'),
    _KeySymbol('asterisk', 'asterisk', '*'),
    _KeySymbol('equal', 'equal', '='),
    _KeySymbol('plus', 'plus', '+'),
    _KeySymbol('comma', 'comma', ','),
    _KeySymbol('minus', 'minus', '-'),
    _KeySymbol('period', 'period', '.'),
    _KeySymbol('slash', 'slash', '/'),
    _KeySymbol('colon', 'colon', ':'),
    _KeySymbol('semicolon', 'semicolon', ';'),
    _KeySymbol('less', 'less', '<'),
    _KeySymbol('greater', 'greater', '>'),
    _KeySymbol('question', 'question', '?'),
    _KeySymbol('at', 'at', '@'),
    _KeySymbol('bracketleft', 'bracketleft', '['),
    _KeySymbol('bracketright', 'bracketright', ']'),
    _KeySymbol('backslash', 'backslash', '\\'),
    _KeySymbol('asciicircum', 'asciicircum', '^'),
    _KeySymbol('underscore', 'underscore', '_'),
    _KeySymbol('grave', 'grave', '`'),
    _KeySymbol('braceleft', 'braceleft', '{'),
    _KeySymbol('bar', 'bar', '|'),
    _KeySymbol('braceright', 'braceright', '}'),
    _KeySymbol('asciitilde', 'asciitilde', '~'),
    _KeySymbol('a', 'a', 'a'),
    _KeySymbol('b', 'b', 'b'),
    _KeySymbol('c', 'c', 'c'),
    _KeySymbol('d', 'd', 'd'),
    _KeySymbol('e', 'e', 'e'),
    _KeySymbol('f', 'f', 'f'),
    _KeySymbol('g', 'g', 'g'),
    _KeySymbol('h', 'h', 'h'),
    _KeySymbol('i', 'i', 'i'),
    _KeySymbol('j', 'j', 'j'),
    _KeySymbol('k', 'k', 'k'),
    _KeySymbol('l', 'l', 'l'),
    _KeySymbol('m', 'm', 'm'),
    _KeySymbol('n', 'n', 'n'),
    _KeySymbol('o', 'o', 'o'),
    _KeySymbol('p', 'p', 'p'),
    _KeySymbol('q', 'q', 'q'),
    _KeySymbol('r', 'r', 'r'),
    _KeySymbol('s', 's', 's'),
    _KeySymbol('t', 't', 't'),
    _KeySymbol('u', 'u', 'u'),
    _KeySymbol('v', 'v', 'v'),
    _KeySymbol('w', 'w', 'w'),
    _KeySymbol('x', 'x', 'x'),
    _KeySymbol('y', 'y', 'y'),
    _KeySymbol('z', 'z', 'z'),
    _KeySymbol('A', 'A', 'A'),
    _KeySymbol('B', 'B', 'B'),
    _KeySymbol('C', 'C', 'C'),
    _KeySymbol('D', 'D', 'D'),
    _KeySymbol('E', 'E', 'E'),
    _KeySymbol('F', 'F', 'F'),
    _KeySymbol('G', 'G', 'G'),
    _KeySymbol('H', 'H', 'H'),
    _KeySymbol('I', 'I', 'I'),
    _KeySymbol('J', 'J', 'J'),
    _KeySymbol('K', 'K', 'K'),
    _KeySymbol('L', 'L', 'L'),
    _KeySymbol('M', 'M', 'M'),
    _KeySymbol('N', 'N', 'N'),
    _KeySymbol('O', 'O', 'O'),
    _KeySymbol('P', 'P', 'P'),
    _KeySymbol('Q', 'Q', 'Q'),
    _KeySymbol('R', 'R', 'R'),
    _KeySymbol('S', 'S', 'S'),
    _KeySymbol('T', 'T', 'T'),
    _KeySymbol('U', 'U', 'U'),
    _KeySymbol('V', 'V', 'V'),
    _KeySymbol('W', 'W', 'W'),
    _KeySymbol('X', 'X', 'X'),
    _KeySymbol('Y', 'Y', 'Y'),
    _KeySymbol('Z', 'Z', 'Z'),
    _KeySymbol('1', '1', '1'),
    _KeySymbol('2', '2', '2'),
    _KeySymbol('3', '3', '3'),
    _KeySymbol('4', '4', '4'),
    _KeySymbol('5', '5', '5'),
    _KeySymbol('6', '6', '6'),
    _KeySymbol('7', '7', '7'),
    _KeySymbol('8', '8', '8'),
    _KeySymbol('9', '9', '9'),
    _KeySymbol('0', '0', '0'),
)

__all__ = ["x11_linux_key_" + key.suffix for key in _KEY_SYMBOLS] + ["get_keyboard_keys_table"]
_LEGACY_NAMES = frozenset(__all__[:-1])

_TABLE: dict[str, int] | None = None
_constants: dict[str, int] = {}
_lock = Lock()


def get_keyboard_keys_table() -> dict[str, int]:
    """Return the shared mutable dict of server-resolved integer keycodes."""
    global _TABLE  # pylint: disable=global-statement  # reason: one module owns this lazy cache
    with _lock:
        if _TABLE is None:
            display = get_display()
            codes = {key.symbol: display.keysym_to_keycode(XK.string_to_keysym(key.symbol))
                     for key in _KEY_SYMBOLS}
            table = {key.public_name: codes[key.symbol] for key in _KEY_SYMBOLS if key.public_name is not None}
            constants = {"x11_linux_key_" + key.suffix: codes[key.symbol] for key in _KEY_SYMBOLS}
            _constants.update(constants)
            _TABLE = table
        return _TABLE


def __getattr__(name: str) -> int:
    """Resolve only the existing legacy key constants."""
    if name not in _LEGACY_NAMES:
        raise AttributeError(name)
    get_keyboard_keys_table()
    return _constants[name]


def __dir__() -> list[str]:
    return sorted(set(globals()) | set(__all__))
