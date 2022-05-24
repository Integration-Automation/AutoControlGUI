from PIL import ImageGrab, Image


def pil_screenshot(file_path: str = None, region: list = None) -> Image:
    """
    :param file_path save screenshot path (None is no save)
    :param region screenshot region (screenshot region on screen)
    """
    if region is not None:
        image = ImageGrab.grab(bbox=region)
    else:
        image = ImageGrab.grab()
    if file_path is not None:
        image.save(file_path)
    return image
