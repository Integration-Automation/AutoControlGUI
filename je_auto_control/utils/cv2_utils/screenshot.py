from PIL import ImageGrab, Image
from typing import List, Optional


def pil_screenshot(file_path: Optional[str] = None, screen_region: Optional[List[int]] = None) -> Image.Image:
    """
    Take a screenshot using PIL (Pillow).
    使用 PIL (Pillow) 擷取螢幕畫面

    :param file_path: (str | None) Path to save the screenshot. If None, do not save.
                      螢幕截圖的存檔路徑，若為 None 則不存檔
    :param screen_region: (list[int] | None) Region to capture [left, top, right, bottom].
                          擷取的螢幕區域 [左, 上, 右, 下]，若為 None 則擷取全螢幕
    :return: PIL.Image.Image object 擷取到的影像物件
    """
    # 擷取螢幕畫面 Capture screen
    if screen_region is not None:
        image = ImageGrab.grab(bbox=screen_region)
    else:
        image = ImageGrab.grab()

    # 如果指定了存檔路徑，則存檔 Save if file_path is provided
    if file_path:
        try:
            image.save(file_path)
        except Exception as e:
            print(f"Failed to save screenshot: {e}")

    return image