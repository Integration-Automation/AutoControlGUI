import cv2
import numpy as np

from je_auto_control.utils.image.screenshot import pil_screenshot
from je_auto_control.utils.exception.exception_tag import screen_get_size
from je_auto_control.utils.exception.exception_tag import screen_screenshot
from je_auto_control.utils.exception.exceptions import AutoControlScreenException
from je_auto_control.wrapper.platform_wrapper import screen


def size():
    """
    get screen size
    """
    try:
        return screen.size()
    except AutoControlScreenException:
        raise AutoControlScreenException(screen_get_size)


def screenshot(file_path: str = None, region: list = None, **kwargs):
    """
    :param file_path screenshot file save path
    :param region screenshot region
    """
    try:
        return cv2.cvtColor(np.array(pil_screenshot(file_path=file_path, region=region)), cv2.COLOR_RGB2BGR)
    except AutoControlScreenException:
        raise AutoControlScreenException(screen_screenshot)
