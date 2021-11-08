import cv2
import numpy as np
from cv2 import cvtColor

from je_auto_control.utils.image.screenshot import pil_screenshot
from je_auto_control.utils.je_auto_control_exception import exception_tag
from je_auto_control.utils.je_auto_control_exception.exceptions import AutoControlScreenException
from je_auto_control.wrapper.platform_wrapper import screen


def size():
    """
    get screen size
    """
    try:
        return screen.size()
    except AutoControlScreenException:
        raise AutoControlScreenException(exception_tag.screen_get_size)


def screenshot(file_path: str = None, region:list = None):
    """
    :param file_path screenshot file save path
    :param region screenshot region
    """
    try:
        return cv2.cvtColor(np.array(pil_screenshot(file_path=file_path, region=region)), cv2.COLOR_RGB2BGR)
    except AutoControlScreenException:
        raise AutoControlScreenException(exception_tag.screen_screenshot)
