import sys
from typing import List, Optional, Tuple

from je_auto_control.utils.cv2_utils.optional import require_cv2
from je_auto_control.utils.cv2_utils.screenshot import pil_screenshot
from je_auto_control.utils.exception.exception_tags import screen_get_size_error_message
from je_auto_control.utils.exception.exception_tags import screen_screenshot_error_message
from je_auto_control.utils.exception.exceptions import AutoControlScreenException
from je_auto_control.utils.logging.logging_instance import autocontrol_logger
from je_auto_control.utils.platform_id import is_windows
from je_auto_control.utils.test_record.record_test_class import record_action_to_list
from je_auto_control.wrapper.platform_wrapper import screen


def screen_size() -> Tuple[int, int]:
    """
    get screen size
    取得螢幕大小
    """
    autocontrol_logger.info("screen_size")
    try:
        record_action_to_list("size", None)
        return screen.size()
    except AutoControlScreenException as error:
        autocontrol_logger.error(f"screen_size failed: {screen_get_size_error_message}")
        raise AutoControlScreenException(screen_get_size_error_message) from error
    except (OSError, RuntimeError, AttributeError, TypeError, ValueError) as error:
        record_action_to_list("size", None, repr(error))
        autocontrol_logger.error(f"screen_size failed: {repr(error)}")
        raise


def screenshot(file_path: Optional[str] = None,
               screen_region: Optional[list] = None) -> List[int]:
    """
    use to capture current screen
    擷取當前螢幕畫面

    :param file_path: screenshot file save path 截圖儲存路徑
    :param screen_region: screenshot region 截圖區域
    """
    autocontrol_logger.info(f"screenshot, file_path: {file_path}, screen_region: {screen_region}")
    # 明寫成 dict,不用 locals():下面的 import 也會出現在 locals() 裡,
    # 錄下來的參數就會多兩個模組物件。
    # Spelled out rather than locals(): the imports below land in locals() too,
    # so the recorded parameters would carry two module objects.
    param = {"file_path": file_path, "screen_region": screen_region}
    # require_cv2 first: without the OpenCV wheel there is no NumPy either,
    # so its ModuleNotFoundError would be the one the caller ended up seeing.
    cv2 = require_cv2()
    import numpy as np  # noqa: E402  # reason: kept off the facade's import path
    try:
        record_action_to_list("AC_screenshot", param)
        return cv2.cvtColor(
            np.array(pil_screenshot(file_path=file_path, screen_region=screen_region)), cv2.COLOR_RGB2BGR)
    except AutoControlScreenException as error:
        autocontrol_logger.error(
            f"screenshot failed, file_path: {file_path}, screen_region: {screen_region}, "
            f"error: {repr(error)}")
        raise AutoControlScreenException(screen_screenshot_error_message + " " + repr(error)) from error
    # cv2.error 只繼承 Exception，不在下面的 tuple 內，會直接逸出這個
    # 承諾拋出 AutoControlScreenException 的介面。
    # cv2.error subclasses only Exception, so it is not covered by the tuple
    # below and would escape this function raw — past callers that were told
    # to expect AutoControlScreenException.
    except cv2.error as error:
        record_action_to_list("AC_screenshot", None, repr(error))
        autocontrol_logger.error(
            f"screenshot failed, file_path: {file_path}, screen_region: {screen_region}, "
            f"error: {repr(error)}")
        raise AutoControlScreenException(
            screen_screenshot_error_message + " " + repr(error)) from error
    except (OSError, RuntimeError, AttributeError, TypeError, ValueError) as error:
        record_action_to_list("AC_screenshot", None, repr(error))
        autocontrol_logger.error(
            f"screenshot failed, file_path: {file_path}, screen_region: {screen_region}, "
            f"error: {repr(error)}")
        raise


def get_pixel(x: int, y: int, hwnd=None):
    """
    取得指定座標的像素顏色
    Get pixel color at given coordinates
    """
    autocontrol_logger.info(f"get_pixel, x: {x}, y: {y}, hwnd: {hwnd}")
    try:
        if hwnd is None:
            return screen.get_pixel(x, y)
        # 只有 Windows 後端接受 hwnd；其他平台會是 TypeError，
        # 因此在這裡給出明確訊息。
        # Only the windows backend takes an hwnd. Passing one elsewhere would
        # surface as a bare TypeError from the backend, so say what is wrong.
        if not is_windows():
            raise AutoControlScreenException(
                f"get_pixel: hwnd is only supported on Windows, "
                f"not {sys.platform}"
            )
        # 這一支明著點名 Windows 後端，而不是走平台縫：縫的合約是 (x, y)，
        # 為了單一平台多出來的第三個參數不該把合約撐開。
        # Named directly rather than called through the seam: the seam's
        # contract is (x, y), and one platform's extra argument does not
        # belong in it.
        from je_auto_control.windows.screen import win32_screen
        return win32_screen.get_pixel(x, y, hwnd)
    except (OSError, RuntimeError, AttributeError, TypeError, ValueError) as error:
        record_action_to_list("AC_get_pixel", None, repr(error))
        autocontrol_logger.error(
            f"get_pixel failed, x: {x}, y: {y}, hwnd: {hwnd}, "
            f"error: {repr(error)}")
        raise
