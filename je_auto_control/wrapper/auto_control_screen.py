import sys

import cv2
import numpy as np

from je_auto_control.utils.image.screenshot import pil_screenshot
from je_auto_control.utils.exception.exception_tag import screen_get_size
from je_auto_control.utils.exception.exception_tag import screen_screenshot
from je_auto_control.utils.exception.exceptions import AutoControlScreenException
from je_auto_control.wrapper.platform_wrapper import screen
from je_auto_control.utils.test_record.record_test_class import record_total


def size():
    """
    get screen size
    """
    try:
        try:
            record_total("size", None)
            return screen.size()
        except AutoControlScreenException:
            raise AutoControlScreenException(screen_get_size)
    except Exception as error:
        record_total("size", None, repr(error))
        print(repr(error), file=sys.stderr)


def screenshot(file_path: str = None, region: list = None):
    """
    use to capture current screen image
    :param file_path screenshot file save path
    :param region screenshot region
    """
    param = locals()
    try:
        try:
            record_total("screenshot", param)
            return cv2.cvtColor(np.array(pil_screenshot(file_path=file_path, region=region)), cv2.COLOR_RGB2BGR)
        except AutoControlScreenException as error:
            raise AutoControlScreenException(screen_screenshot + repr(error))
    except Exception as error:
        record_total("screenshot", None, repr(error))
        print(repr(error), file=sys.stderr)
