from PIL import Image
from typing import List, Optional

from je_auto_control.utils.cv2_utils.screen_grabber import image_grabber
from je_auto_control.utils.exception.exceptions import AutoControlScreenException


def _validate_region(screen_region: List[int]) -> None:
    """Reject a region PIL would turn into an empty image.

    擷取區域必須是 [左, 上, 右, 下] 且寬高都大於 0。
    A zero-area bbox makes ImageGrab return an empty image, and the caller's
    cv2.cvtColor then raises a raw ``cv2.error`` — which subclasses only
    ``Exception``, so it escapes the screenshot wrapper's except tuple and
    reaches callers that were told to expect AutoControlScreenException.
    Reject it here, at the boundary, with a message that says what is wrong.
    """
    try:
        left, top, right, bottom = (int(value) for value in screen_region)
    except (TypeError, ValueError) as error:
        raise AutoControlScreenException(
            f"screen_region must be 4 ints [left, top, right, bottom]; "
            f"got {screen_region!r}"
        ) from error
    if right <= left or bottom <= top:
        raise AutoControlScreenException(
            f"screen_region must have positive width and height; got "
            f"[{left}, {top}, {right}, {bottom}] "
            f"(width={right - left}, height={bottom - top})"
        )


def pil_screenshot(file_path: Optional[str] = None, screen_region: Optional[List[int]] = None) -> Image.Image:
    """
    Take a screenshot through the platform's capture backend.
    透過平台擷取後端擷取螢幕畫面

    Kept named ``pil_screenshot`` (and still returning a Pillow image)
    because it is public API, but the grabber is now chosen per platform:
    Pillow's ``ImageGrab`` reads the X11 root window, which under Wayland
    belongs to XWayland and holds none of the native Wayland windows. See
    :mod:`je_auto_control.utils.cv2_utils.screen_grabber`.

    :param file_path: (str | None) Path to save the screenshot. If None, do not save.
                      螢幕截圖的存檔路徑，若為 None 則不存檔
    :param screen_region: (list[int] | None) Region to capture [left, top, right, bottom].
                          擷取的螢幕區域 [左, 上, 右, 下]，若為 None 則擷取全螢幕
    :return: PIL.Image.Image object 擷取到的影像物件
    """
    # 擷取螢幕畫面 Capture screen
    grabber = image_grabber()
    if screen_region is not None:
        _validate_region(screen_region)
        image = grabber.grab(bbox=screen_region)
    else:
        image = grabber.grab()

    # 如果指定了存檔路徑，則存檔 Save if file_path is provided.
    # Fail fast: a swallowed save error would leave the caller believing the
    # requested screenshot file exists when it does not.
    if file_path:
        try:
            image.save(file_path)
        except (OSError, ValueError) as error:
            raise AutoControlScreenException(
                f"Failed to save screenshot to {file_path!r}: {error}"
            ) from error

    return image