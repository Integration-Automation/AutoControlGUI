import sys
import time

from je_auto_control.utils.exception.exception_tags import linux_import_error_message
from je_auto_control.utils.exception.exceptions import AutoControlException

# === 平台檢查 Platform Check ===
# 僅允許在 Linux 環境執行，否則拋出例外
if sys.platform not in ["linux", "linux2"]:
    raise AutoControlException(linux_import_error_message)

from je_auto_control.linux_with_x11.core.utils.x11_linux_display import display
from Xlib.ext.xtest import fake_input
from Xlib import X, protocol


def press_key(keycode: int) -> None:
    """
    Press a key using X11 fake_input
    使用 X11 fake_input 模擬按下鍵盤按鍵

    :param keycode: (int) The keycode to press 要按下的鍵盤代碼
    """
    if not isinstance(keycode, int):
        raise ValueError("Keycode must be an integer 鍵盤代碼必須是整數")

    time.sleep(0.01)  # Small delay to ensure event stability 確保事件穩定的小延遲
    fake_input(display, X.KeyPress, keycode)
    display.sync()


def release_key(keycode: int) -> None:
    """
    Release a key using X11 fake_input
    使用 X11 fake_input 模擬釋放鍵盤按鍵

    :param keycode: (int) The keycode to release 要釋放的鍵盤代碼
    """
    if not isinstance(keycode, int):
        raise ValueError("Keycode must be an integer 鍵盤代碼必須是整數")

    time.sleep(0.01)
    fake_input(display, X.KeyRelease, keycode)
    display.sync()


def send_key_event_to_window(window_id: int, keycode: int) -> None:
    """
    Send key press + release event directly to a specific window
    將鍵盤按下與釋放事件直接送到指定視窗

    :param window_id: (int) Target window ID 目標視窗 ID
    :param keycode: (int) Keycode to send 要送出的鍵盤代碼
    """
    if not isinstance(window_id, int):
        raise ValueError("Window ID must be an integer 視窗 ID 必須是整數")
    if not isinstance(keycode, int):
        raise ValueError("Keycode must be an integer 鍵盤代碼必須是整數")

    # 建立目標視窗物件 Create target window object
    window = display.create_resource_object("window", window_id)

    # 建立 KeyPress 事件 Create KeyPress event
    event = protocol.event.KeyPress(
        time=X.CurrentTime,
        root=display.screen().root,
        window=window,
        same_screen=1,
        child=X.NONE,
        root_x=0, root_y=0, event_x=0, event_y=0,
        state=0,
        detail=keycode
    )

    # 傳送 KeyPress 事件 Send KeyPress event
    window.send_event(event, propagate=True)

    # 修改為 KeyRelease 並傳送 Modify to KeyRelease and send
    event.type = X.KeyRelease
    window.send_event(event, propagate=True)

    # 刷新事件 Flush events
    display.flush()