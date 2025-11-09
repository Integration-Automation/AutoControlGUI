import sys

from je_auto_control.utils.exception.exception_tags import windows_import_error_message
from je_auto_control.utils.exception.exceptions import AutoControlException

if sys.platform not in ["win32", "cygwin", "msys"]:
    raise AutoControlException(windows_import_error_message)

# windows mouse virtual keycode


WIN32_MOVE: int = 0x0001
WIN32_LEFTDOWN: int = 0x0002
WIN32_LEFTUP: int = 0x0004
WIN32_RIGHTDOWN: int = 0x0008
WIN32_RIGHTUP: int = 0x0010
WIN32_MIDDLEDOWN: int = 0x0020
WIN32_MIDDLEUP: int = 0x0040
WIN32_DOWN: int = 0x0080
WIN32_XUP: int = 0x0100
WIN32_WHEEL: int = 0x0800
WIN32_HWHEEL: int = 0x1000
WIN32_ABSOLUTE: int = 0x8000
WIN32_XBUTTON1: int = 0x0001
WIN32_XBUTTON2: int = 0x0002

WIN32_VK_LBUTTON: int = 0x01
WIN32_VK_RBUTTON: int = 0x02
WIN32_VK_MBUTTON: int = 0x04
WIN32_VK_XBUTTON1: int = 0x05
WIN32_VK_XBUTTON2: int = 0x06

"""
windows keyboard virtual keycode
"""

WIN32_EventF_EXTENDEDKEY: int = 0x0001
WIN32_EventF_KEYUP: int = 0x0002
WIN32_EventF_UNICODE: int = 0x0004
WIN32_EventF_SCANCODE: int = 0x0008

WIN32_VkToVSC: int = 0
WIN32_VK_CANCEL: int = 0x03
WIN32_VK_BACK: int = 0x08  # BACKSPACE key
WIN32_VK_TAB: int = 0x09  # TAB key
WIN32_VK_CLEAR: int = 0x0C  # CLEAR key
WIN32_VK_RETURN: int = 0x0D  # ENTER key
WIN32_VK_SHIFT: int = 0x10  # SHIFT key
WIN32_VK_CONTROL: int = 0x11  # CTRL key
WIN32_VK_Menu: int = 0x12  # ALT key
WIN32_VK_PAUSE: int = 0x13  # PAUSE key
WIN32_VK_CAPITAL: int = 0x14  # CAPS LOCK key
WIN32_VK_KANA: int = 0x15
WIN32_VK_IME_ON: int = 0x16
WIN32_VK_JUNJA: int = 0x17
WIN32_VK_FINAL: int = 0x18  # ESC key
WIN32_VK_HANJA: int = 0x19
WIN32_VK_IME_OFF: int = 0x1A
WIN32_VK_ESCAPE: int = 0x1B
WIN32_VK_CONVERT: int = 0x1C
WIN32_VK_NONCONVERT: int = 0x1D
WIN32_VK_ACCEPT: int = 0x1E
WIN32_VK_MODECHANGE: int = 0x1F
WIN32_VK_SPACE: int = 0x20  # SPACEBAR
WIN32_VK_PRIOR: int = 0x21  # PAGE UP key
WIN32_VK_NEXT: int = 0x22  # PAGE DOWN key
WIN32_VK_END: int = 0x23  # END key
WIN32_VK_HOME: int = 0x24  # HOME key
WIN32_VK_LEFT: int = 0x25  # LEFT ARROW key
WIN32_VK_UP: int = 0x26
WIN32_VK_RIGHT: int = 0x27
WIN32_VK_DOWN: int = 0x28
WIN32_VK_SELECT: int = 0x29
WIN32_VK_PRINT: int = 0x2A
WIN32_VK_EXECUTE: int = 0x2B
WIN32_VK_SNAPSHOT: int = 0x2C
WIN32_VK_INSERT: int = 0x2D
WIN32_VK_DELETE: int = 0x2E
WIN32_VK_HELP: int = 0x2F
WIN32_key0: int = 0x30
WIN32_key1: int = 0x31
WIN32_key2: int = 0x32
WIN32_key3: int = 0x33
WIN32_key4: int = 0x34
WIN32_key5: int = 0x35
WIN32_key6: int = 0x36
WIN32_key7: int = 0x37
WIN32_key8: int = 0x38
WIN32_key9: int = 0x39
WIN32_keyA: int = 0x41
WIN32_keyB: int = 0x42
WIN32_keyC: int = 0x43
WIN32_keyD: int = 0x44
WIN32_keyE: int = 0x45
WIN32_keyF: int = 0x46
WIN32_keyG: int = 0x47
WIN32_keyH: int = 0x48
WIN32_keyI: int = 0x49
WIN32_keyJ: int = 0x4A
WIN32_keyK: int = 0x4B
WIN32_keyL: int = 0x4C
WIN32_keyM: int = 0X4D
WIN32_keyN: int = 0x4E
WIN32_keyO: int = 0x4F
WIN32_keyP: int = 0x50
WIN32_keyQ: int = 0x51
WIN32_keyR: int = 0x52
WIN32_keyS: int = 0x53
WIN32_keyT: int = 0x54
WIN32_keyU: int = 0x55
WIN32_keyV: int = 0x56
WIN32_keyW: int = 0x57
WIN32_keyX: int = 0x58
WIN32_keyY: int = 0x59
WIN32_keyZ: int = 0x5A
WIN32_VK_LWIN: int = 0x5B  # Left Windows key (Natural keyboard)
WIN32_VK_RWIN: int = 0x5C  # Right Windows key (Natural keyboard)
WIN32_VK_APPS: int = 0x5D  # Applications key (Natural keyboard)
WIN32_VK_SLEEP: int = 0x5F  # Computer Sleep key
WIN32_VK_NUMPAD0: int = 0x60  # Numeric keypad 0 key
WIN32_VK_NUMPAD1: int = 0x61
WIN32_VK_NUMPAD2: int = 0x62
WIN32_VK_NUMPAD3: int = 0x63
WIN32_VK_NUMPAD4: int = 0x64
WIN32_VK_NUMPAD5: int = 0x65
WIN32_VK_NUMPAD6: int = 0x66
WIN32_VK_NUMPAD7: int = 0x67
WIN32_VK_NUMPAD8: int = 0x68
WIN32_VK_NUMPAD9: int = 0x69
WIN32_VK_MULTIPLY: int = 0x6A  # Multiply key
WIN32_VK_ADD: int = 0x6B  # Add key
WIN32_VK_SEPARATOR: int = 0x6C  # Separator key
WIN32_VK_SUBTRACT: int = 0x6D  # Subtract key
WIN32_VK_DECIMAL: int = 0x6E  # Decimal key
WIN32_VK_DIVIDE: int = 0x6F  # VK_DIVIDE
WIN32_VK_F1: int = 0x70  # F1
WIN32_VK_F2: int = 0x71
WIN32_VK_F3: int = 0x72
WIN32_VK_F4: int = 0x73
WIN32_VK_F5: int = 0x74
WIN32_VK_F6: int = 0x75
WIN32_VK_F7: int = 0x76
WIN32_VK_F8: int = 0x77
WIN32_VK_F9: int = 0x78
WIN32_VK_F10: int = 0x79
WIN32_VK_F11: int = 0x7A
WIN32_VK_F12: int = 0x7B
WIN32_VK_F13: int = 0x7C
WIN32_VK_F14: int = 0x7D
WIN32_VK_F15: int = 0x7E
WIN32_VK_F16: int = 0x7F
WIN32_VK_F17: int = 0x80
WIN32_VK_F18: int = 0x81
WIN32_VK_F19: int = 0x82
WIN32_VK_F20: int = 0x83
WIN32_VK_F21: int = 0x84
WIN32_VK_F22: int = 0x85
WIN32_VK_F23: int = 0x86
WIN32_VK_F24: int = 0x87
WIN32_VK_NUMLOCK: int = 0x90  # NUM LOCK key
WIN32_VK_SCROLL: int = 0x91  # SCROLL LOCK key
WIN32_VK_LSHIFT: int = 0xA0  # Left SHIFT key
WIN32_VK_RSHIFT: int = 0xA1
WIN32_VK_LCONTROL: int = 0xA2  # Left CONTROL key
WIN32_VK_RCONTROL: int = 0xA3  # Right CONTROL key
WIN32_VK_LMENU: int = 0xA4  # Left MENU key
WIN32_VK_RMENU: int = 0xA5  # Right MENU key
WIN32_VK_BROWSER_BACK: int = 0xA6  # Browser Back key
WIN32_VK_BROWSER_FORWARD: int = 0xA7  # Browser Forward key
WIN32_VK_BROWSER_REFRESH: int = 0xA8  # Browser Refresh key
WIN32_VK_BROWSER_STOP: int = 0xA9  # Browser Stop key
WIN32_VK_BROWSER_SEARCH: int = 0xAA  # Browser Search key
WIN32_VK_BROWSER_FAVORITES: int = 0xAB  # Browser Favorites key
WIN32_VK_VOLUME_MUTE: int = 0xAD
WIN32_VK_VOLUME_DOWN: int = 0xAE
WIN32_VK_VOLUME_UP: int = 0xAF
WIN32_VK_MEDIA_NEXT_TRACK: int = 0xB0
WIN32_VK_MEDIA_PREV_TRACK: int = 0xB1
WIN32_VK_MEDIA_STOP: int = 0xB2
WIN32_VK_MEDIA_PLAY_PAUSE: int = 0xB3
WIN32_VK_LAUNCH_MAIL: int = 0xB4
WIN32_VK_LAUNCH_MEDIA_SELECT: int = 0xB5
WIN32_VK_LAUNCH_APP1: int = 0xB6
WIN32_VK_LAUNCH_APP2: int = 0xB7