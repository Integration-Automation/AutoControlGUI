from typing import Tuple, List

import cv2
import numpy as np

from je_auto_control.utils.exception.exception_tags import screen_get_size
from je_auto_control.utils.exception.exception_tags import screen_screenshot
from je_auto_control.utils.exception.exceptions import AutoControlScreenException
from je_auto_control.utils.image.screenshot import pil_screenshot
from je_auto_control.utils.logging.loggin_instance import auto_control_logger
from je_auto_control.utils.test_record.record_test_class import record_action_to_list
from je_auto_control.wrapper.platform_wrapper import screen


def screen_size() -> Tuple[int, int]:
    """
    get screen size
    """
    auto_control_logger.info("screen_size")
    try:
        try:
            record_action_to_list("size", None)
            return screen.size()
        except AutoControlScreenException:
            auto_control_logger.error(f"screen_size, failed: {repr(AutoControlScreenException(screen_get_size))}")
            raise AutoControlScreenException(screen_get_size)
    except Exception as error:
        record_action_to_list("size", None, repr(error))
        auto_control_logger.error(f"screen_size, failed: {repr(error)}")


def screenshot(file_path: str = None, screen_region: list = None) -> List[int]:
    """
    use to capture current screen image
    :param file_path screenshot file save path
    :param screen_region screenshot screen_region
    """
    auto_control_logger.info(f"screen_size, file_path: {file_path}, screen_region: {screen_region}")
    param = locals()
    try:
        try:
            record_action_to_list("screenshot", param)
            return cv2.cvtColor(
                np.array(pil_screenshot(file_path=file_path, screen_region=screen_region)), cv2.COLOR_RGB2BGR)
        except AutoControlScreenException as error:
            auto_control_logger.info(
                f"screen_size, file_path: {file_path}, screen_region: {screen_region}, "
                f"failed: {AutoControlScreenException(screen_screenshot + ' ' + repr(error))}")
            raise AutoControlScreenException(screen_screenshot + " " + repr(error))
    except Exception as error:
        record_action_to_list("screenshot", None, repr(error))
        auto_control_logger.info(
            f"screen_size, file_path: {file_path}, screen_region: {screen_region}, "
            f"failed: {repr(error)}")
