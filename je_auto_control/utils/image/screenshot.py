from PIL import ImageGrab, Image


def pil_screenshot(file_path: str = None, screen_region: list = None) -> Image:
    """
    use pil to make a screenshot
    :param file_path save screenshot path (None is no save)
    :param screen_region screenshot screen_region on screen [left, top, right, bottom]
    """
    if screen_region is not None:
        image = ImageGrab.grab(bbox=screen_region)
    else:
        image = ImageGrab.grab()
    if file_path is not None:
        image.save(file_path)
    return image
