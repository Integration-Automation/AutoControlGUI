from typing import List, Tuple, Optional, Union

from je_auto_control.utils.cv2_utils import template_detection
from je_auto_control.utils.cv2_utils.screenshot import pil_screenshot
from je_auto_control.utils.exception.exception_tags import cant_find_image_error_message, find_image_error_variable_error_message
from je_auto_control.utils.exception.exceptions import ImageNotFoundException
from je_auto_control.utils.logging.loggin_instance import autocontrol_logger
from je_auto_control.utils.test_record.record_test_class import record_action_to_list
from je_auto_control.wrapper.auto_control_mouse import click_mouse, set_mouse_position


def locate_all_image(image, detect_threshold: float = 1.0,
                     draw_image: bool = False) -> List[List[int]]:
    """
    找出螢幕上所有符合的影像位置
    Locate all matching images on screen

    :param image: 影像檔路徑或 PIL Image
    :param detect_threshold: 偵測精度 (0.0 ~ 1.0)
    :param draw_image: 是否在結果上標記
    :return: 符合影像的區域清單 [[x1, y1, x2, y2], ...]
    """
    autocontrol_logger.info(f"Find multi images {image}, threshold={detect_threshold}")
    try:
        image_data_array = template_detection.find_image_multi(image, detect_threshold, draw_image)
        if image_data_array[0]:
            record_action_to_list("locate_all_image", {"image": image, "threshold": detect_threshold})
            return image_data_array[1]
        raise ImageNotFoundException(f"{cant_find_image_error_message} / {image}")
    except Exception as error:
        record_action_to_list("locate_all_image", {"image": image}, repr(error))
        autocontrol_logger.error(f"locate_all_image failed: {repr(error)}")
        raise


def locate_image_center(image, detect_threshold: float = 1.0,
                        draw_image: bool = False) -> Tuple[int, int]:
    """
    找出單一影像並回傳中心座標
    Locate image and return its center position

    :return: (center_x, center_y)
    """
    autocontrol_logger.info(f"Locate image center {image}, threshold={detect_threshold}")
    try:
        image_data_array = template_detection.find_image(image, detect_threshold, draw_image)
        if image_data_array[0]:
            x1, y1, x2, y2 = image_data_array[1]
            center_x = int((x1 + x2) / 2)
            center_y = int((y1 + y2) / 2)
            record_action_to_list("locate_image_center", {"image": image, "threshold": detect_threshold})
            return center_x, center_y
        raise ImageNotFoundException(f"{cant_find_image_error_message} / {image}")
    except Exception as error:
        record_action_to_list("locate_image_center", {"image": image}, repr(error))
        autocontrol_logger.error(f"locate_image_center failed: {repr(error)}")
        raise


def locate_and_click(image, mouse_keycode: Union[int, str],
                     detect_threshold: float = 1.0,
                     draw_image: bool = False) -> Tuple[int, int]:
    """
    找出影像後自動移動滑鼠並點擊
    Locate image and click its center

    :return: (center_x, center_y)
    """
    autocontrol_logger.info(f"Locate and click {image}, keycode={mouse_keycode}, threshold={detect_threshold}")
    try:
        image_data_array = template_detection.find_image(image, detect_threshold, draw_image)
        if image_data_array[0]:
            x1, y1, x2, y2 = image_data_array[1]
            center_x = int((x1 + x2) / 2)
            center_y = int((y1 + y2) / 2)
            set_mouse_position(center_x, center_y)
            click_mouse(mouse_keycode)
            record_action_to_list("locate_and_click", {"image": image, "threshold": detect_threshold})
            return center_x, center_y
        raise ImageNotFoundException(f"{cant_find_image_error_message} / {image}")
    except Exception as error:
        record_action_to_list("locate_and_click", {"image": image}, repr(error))
        autocontrol_logger.error(f"locate_and_click failed: {repr(error)}")
        raise


def screenshot(file_path: Optional[str] = None, region: Optional[List[int]] = None):
    """
    擷取螢幕畫面
    Take a screenshot

    :param file_path: 儲存路徑 (None = 不儲存)
    :param region: 擷取區域 [x1, y1, x2, y2]
    :return: PIL Image
    """
    autocontrol_logger.info(f"screenshot, file={file_path}, region={region}")
    try:
        record_action_to_list("screenshot", {"file_path": file_path, "region": region})
        return pil_screenshot(file_path, region)
    except Exception as error:
        record_action_to_list("screenshot", {"file_path": file_path, "region": region}, repr(error))
        autocontrol_logger.error(f"screenshot failed: {repr(error)}")
        raise