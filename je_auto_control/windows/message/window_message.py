from je_auto_control.windows.core.utils.win32_ctype_input import user32
from je_auto_control.windows.window.window_hwnd import FindWindowW

PostMessageW = user32.PostMessageW
SendMessageW = user32.SendMessageW

messages = {
    "WM_ACTIVATEAPP": 0x001C,
    "WM_CANCELMODE": 0x001F,
    "WM_CHILDACTIVATE": 0x0022,
    "WM_CLOSE": 0x0010,
    "WM_COMPACTING": 0x0041,
    "WM_CREATE": 0x0001,
    "WM_DESTROY": 0x0002,
    "WM_ENABLE": 0x000A,
    "WM_ENTERSIZEMOVE": 0x0231,
    "WM_EXITSIZEMOVE": 0x0232,
    "WM_GETICON": 0x007F,
    "WM_GETMINMAXINFO": 0x0024,
    "WM_INPUTLANGCHANGE": 0x0051,
    "WM_INPUTLANGCHANGEREQUEST": 0x0050,
    "WM_MOVE": 0x0003,
    "WM_MOVING": 0x0216,
    "WM_NCACTIVATE": 0x0086,
    "WM_NCCALCSIZE": 0x0083,
    "WM_NCCREATE": 0x0081,
    "WM_NCDESTROY": 0x0082,
    "WM_NULL": 0x0000,
    "WM_QUERYDRAGICON": 0x0037,
    "WM_QUERYOPEN": 0x0013,
    "WM_QUIT": 0x0012,
    "WM_SHOWWINDOW": 0x0018,
    "WM_SIZE": 0x0005,
    "WM_SIZING": 0x0214,
    "WM_STYLECHANGED": 0x007D,
    "WM_STYLECHANGING": 0x007C,
    "WM_THEMECHANGED": 0x031A,
    "WM_USERCHANGED": 0x0054,
    "WM_WINDOWPOSCHANGED": 0x0047,
    "WM_WINDOWPOSCHANGING": 0x0046
}


def send_message_to_window(window_name: str, action_message: int,
                           key_code_1: int, key_code_2: int):
    _hwnd = FindWindowW(window_name)
    post_status = SendMessageW(_hwnd, action_message, key_code_1, key_code_2)
    return _hwnd, post_status


def send_message_to_window_hwnd(_hwnd, action_message: int,
                                key_code_1: int, key_code_2: int):
    post_status = SendMessageW(_hwnd, action_message, key_code_1, key_code_2)
    return _hwnd, post_status


def post_message_to_window(window_name: str, action_message: int,
                           key_code_1: int, key_code_2: int):
    _hwnd = FindWindowW(window_name)
    post_status = PostMessageW(_hwnd, action_message, key_code_1, key_code_2)
    return _hwnd, post_status


def post_message_to_window_hwnd(_hwnd, action_message: int,
                                key_code_1: int, key_code_2: int):
    post_status = PostMessageW(_hwnd, action_message, key_code_1, key_code_2)
    return _hwnd, post_status
