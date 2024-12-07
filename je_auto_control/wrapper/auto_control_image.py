from typing import List, Union

from je_auto_control.utils.cv2_utils import template_detection
from je_auto_control.utils.cv2_utils.screenshot import pil_screenshot
from je_auto_control.utils.exception.exception_tags import cant_find_image
from je_auto_control.utils.exception.exception_tags import find_image_error_variable
from je_auto_control.utils.exception.exceptions import ImageNotFoundException
from je_auto_control.utils.logging.loggin_instance import autocontrol_logger
from je_auto_control.utils.test_record.record_test_class import record_action_to_list
from je_auto_control.wrapper.auto_control_mouse import click_mouse
from je_auto_control.wrapper.auto_control_mouse import set_mouse_position


def locate_all_image(image, detect_threshold: [float, int] = 1,
                     draw_image: bool = False) -> List[int]:
    """
     use to locate all cv2_utils that detected and then return detected images list
    :param image which cv2_utils we want to find on screen (png or PIL ImageGrab.grab())
    :param detect_threshold detect precision 0.0 ~ 1.0; 1 is absolute equal (float or int)
    :param draw_image draw detect tag on return cv2_utils (bool)
    """
    autocontrol_logger.info(
        f"Find multi cv2_utils {image}, with threshold {detect_threshold}"
    )
    param = locals()
    try:
        try:
            image_data_array = template_detection.find_image_multi(image, detect_threshold, draw_image)
        except ImageNotFoundException as error:
            autocontrol_logger.error(
                f"Find multi cv2_utils {image}, with threshold {detect_threshold} failed. "
                f"failed: {repr(find_image_error_variable + ' ' + repr(error) + ' ' + str(image))}")
            raise ImageNotFoundException(find_image_error_variable + " " + repr(error) + " " + str(image))
        if image_data_array[0] is True:
            record_action_to_list("locate_all_image", param)
            return image_data_array[1]
        else:
            autocontrol_logger.error(
                f"Find multi cv2_utils {image}, with threshold {detect_threshold} failed. "
                f"failed: {repr(ImageNotFoundException(cant_find_image + ' / ' + repr(image)))}")
            raise ImageNotFoundException(cant_find_image + " / " + repr(image))
    except Exception as error:
        record_action_to_list("locate_all_image", param, repr(error))
        autocontrol_logger.error(
            f"Find multi cv2_utils {image}, with threshold {detect_threshold} failed. "
            f"failed: {repr(error)}")


def locate_image_center(image, detect_threshold: [float, int] = 1, draw_image: bool = False) -> List[Union[int, int]]:
    """
    use to locate cv2_utils and return cv2_utils center position
    :param image which cv2_utils we want to find on screen (png or PIL ImageGrab.grab())
    :param detect_threshold detect precision 0.0 ~ 1.0; 1 is absolute equal (float or int)
    :param draw_image draw detect tag on return cv2_utils (bool)
    """
    autocontrol_logger.info(
        f"Try to locate cv2_utils center {image} with threshold {detect_threshold}")
    param = locals()
    try:
        try:
            image_data_array = template_detection.find_image(image, detect_threshold, draw_image)
        except ImageNotFoundException as error:
            autocontrol_logger.error(
                f"Locate cv2_utils center failed. cv2_utils: {image}, with threshold {detect_threshold}, "
                f"{repr(ImageNotFoundException(find_image_error_variable + ' ' + repr(error) + ' ' + str(image)))}"
            )
            raise ImageNotFoundException(find_image_error_variable + " " + repr(error) + " " + str(image))
        if image_data_array[0] is True:
            height = image_data_array[1][2] - image_data_array[1][0]
            width = image_data_array[1][3] - image_data_array[1][1]
            center = [int(height / 2), int(width / 2)]
            record_action_to_list("locate_image_center", param)
            return [int(image_data_array[1][0] + center[0]), int(image_data_array[1][1] + center[1])]
        else:
            autocontrol_logger.error(
                f"Locate cv2_utils center failed. cv2_utils: {image}, with threshold {detect_threshold}, "
                f"failed: {repr(ImageNotFoundException(cant_find_image + ' / ' + repr(image)))}"
            )
            raise ImageNotFoundException(cant_find_image + " / " + repr(image))
    except Exception as error:
        record_action_to_list("locate_image_center", param, repr(error))
        autocontrol_logger.error(
            f"Locate cv2_utils center failed. cv2_utils: {image}, with threshold {detect_threshold}, "
            f"failed: {repr(error)}")


def locate_and_click(
        image, mouse_keycode: [int, str],
        detect_threshold: [float, int] = 1,
        draw_image: bool = False) -> List[Union[int, int]]:
    """
    use to locate cv2_utils and click cv2_utils center position and the return cv2_utils center position
    :param image which cv2_utils we want to find on screen (png or PIL ImageGrab.grab())
    :param mouse_keycode which mouse keycode we want to click
    :param detect_threshold detect precision 0.0 ~ 1.0; 1 is absolute equal (float or int)
    :param draw_image draw detect tag on return cv2_utils (bool)
    """
    autocontrol_logger.info(
        f"locate_and_click, cv2_utils: {image}, keycode: {mouse_keycode}, detect threshold: {detect_threshold}, "
        f"draw cv2_utils: {draw_image}"
    )
    param = locals()
    try:
        try:
            image_data_array = template_detection.find_image(image, detect_threshold, draw_image)
        except ImageNotFoundException:
            autocontrol_logger.error(
                f"Locate and click failed, cv2_utils: {image}, keycode: {mouse_keycode}, "
                f"detect_threshold: {detect_threshold}, "
                f"failed: {repr(ImageNotFoundException(find_image_error_variable))}"
            )
            raise ImageNotFoundException(find_image_error_variable)
        if image_data_array[0] is True:
            height = image_data_array[1][2] - image_data_array[1][0]
            width = image_data_array[1][3] - image_data_array[1][1]
            center = [int(height / 2), int(width / 2)]
            image_center_x = image_data_array[1][0] + center[0]
            image_center_y = image_data_array[1][1] + center[1]
            set_mouse_position(int(image_center_x), int(image_center_y))
            click_mouse(mouse_keycode)
            record_action_to_list("locate_and_click", param)
            return [int(image_center_x), int(image_center_y)]
        else:
            autocontrol_logger.error(
                f"Locate and click failed, cv2_utils: {image}, keycode: {mouse_keycode}, "
                f"detect_threshold: {detect_threshold}, "
                f"failed: {repr(ImageNotFoundException(cant_find_image + ' / ' + repr(image)))}"
            )
            raise ImageNotFoundException(cant_find_image + " / " + repr(image))
    except Exception as error:
        record_action_to_list("locate_and_click", param, repr(error))
        autocontrol_logger.error(
            f"Locate and click failed, cv2_utils: {image}, keycode: {mouse_keycode}, "
            f"detect_threshold: {detect_threshold}, "
            f"failed: {repr(error)}"
        )


def screenshot(file_path: str = None, region: list = None) -> List[Union[int, int]]:
    """
    use to get now screen cv2_utils return cv2_utils
    :param file_path save screenshot path (None is no save)
    :param region screenshot screen_region (screenshot screen_region on screen)
    """
    autocontrol_logger.info(
        f"screenshot, file path: {file_path}, region: {region}"
    )
    param = locals()
    try:
        record_action_to_list("screenshot", param)
        return pil_screenshot(file_path, region)
    except Exception as error:
        autocontrol_logger.error(
            f"Screenshot failed, file path: {file_path}, region: {region}, "
            f"failed: {repr(error)}"
        )
        record_action_to_list("screenshot", param, repr(error))
