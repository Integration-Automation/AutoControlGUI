from PIL import ImageGrab


def pil_screenshot(file_path: str = None, region: list = None):
    """
    :param file_path save screenshot path
    :param region screenshot region
    """
    if region is not None:
        image = ImageGrab.grab(bbox=region)
    else:
        image = ImageGrab.grab()
    if file_path is not None:
        image.save(file_path)
    return image
