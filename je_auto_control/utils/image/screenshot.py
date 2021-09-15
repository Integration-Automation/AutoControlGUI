from PIL import ImageGrab

from je_auto_control.utils.je_auto_control_exception import exception_tag
from je_auto_control.utils.je_auto_control_exception.exceptions import AutoControlScreenException


def pil_screenshot(file_path=None, region=None):
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

