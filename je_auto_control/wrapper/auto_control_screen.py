import sys
from typing import Tuple, List

import cv2
import numpy as np

from je_auto_control.utils.exception.exception_tags import screen_get_size
from je_auto_control.utils.exception.exception_tags import screen_screenshot
from je_auto_control.utils.exception.exceptions import AutoControlScreenException
from je_auto_control.utils.image.screenshot import pil_screenshot
from je_auto_control.utils.test_record.record_test_class import record_action_to_list
from je_auto_control.wrapper.platform_wrapper import screen


def size() -> Tuple[int, int]:
    """
    get screen size
    """
    try:
        try:
            record_action_to_list("size", None)
            return screen.size()
        except AutoControlScreenException:
            raise AutoControlScreenException(screen_get_size)
    except Exception as error:
        record_action_to_list("size", None, repr(error))
        print(repr(error), file=sys.stderr)


def screenshot(file_path: str = None, screen_region: list = None) -> List[int]:
    """
    use to capture current screen image
    :param file_path screenshot file save path
    :param screen_region screenshot screen_region
    """
    param = locals()
    try:
        try:
            record_action_to_list("screenshot", param)
            return cv2.cvtColor(np.array(pil_screenshot(file_path=file_path, screen_region=screen_region)), cv2.COLOR_RGB2BGR)
        except AutoControlScreenException as error:
            raise AutoControlScreenException(screen_screenshot + " " + repr(error))
    except Exception as error:
        record_action_to_list("screenshot", None, repr(error))
        print(repr(error), file=sys.stderr)
