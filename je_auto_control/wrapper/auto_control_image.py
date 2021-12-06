from je_auto_control.utils.image import template_detection
from je_auto_control.utils.exception.exception_tag import cant_find_image
from je_auto_control.utils.exception.exception_tag import find_image_error_variable
from je_auto_control.utils.exception.exceptions import ImageNotFoundException
from je_auto_control.wrapper.auto_control_mouse import click_mouse
from je_auto_control.wrapper.auto_control_mouse import set_position


def locate_all_image(image, detect_threshold: float = 1, draw_image: bool = False, **kwargs):
    """
    :param image which image we want to find on screen
    :param detect_threshold detect precision 0.0 ~ 1.0; 1 is absolute equal
    :param draw_image draw detect tag on return image
    """
    try:
        image_data_array = template_detection.find_image_multi(image, detect_threshold, draw_image)
    except ImageNotFoundException:
        raise ImageNotFoundException(find_image_error_variable)
    if image_data_array[0] is True:
        return image_data_array[1]
    else:
        raise ImageNotFoundException(cant_find_image)


def locate_image_center(image, detect_threshold: float = 1, draw_image: bool = False, **kwargs):
    """
    :param image which image we want to find on screen
    :param detect_threshold detect precision 0.0 ~ 1.0; 1 is absolute equal
    :param draw_image draw detect tag on return image
    """
    try:
        image_data_array = template_detection.find_image(image, detect_threshold, draw_image)
    except ImageNotFoundException:
        raise ImageNotFoundException(find_image_error_variable)
    if image_data_array[0] is True:
        height = image_data_array[1][2] - image_data_array[1][0]
        width = image_data_array[1][3] - image_data_array[1][1]
        center = [int(height / 2), int(width / 2)]
        return [image_data_array[1][0] + center[0], image_data_array[1][1] + center[1]]
    else:
        raise ImageNotFoundException(cant_find_image)


def locate_and_click(image, mouse_keycode: [int, str], detect_threshold: float = 1, draw_image: bool = False, **kwargs):
    """
    :param image which image we want to find on screen
    :param mouse_keycode which mouse keycode we want to click
    :param detect_threshold detect precision 0.0 ~ 1.0; 1 is absolute equal
    :param draw_image draw detect tag on return image
    """
    try:
        image_data_array = template_detection.find_image(image, detect_threshold, draw_image)
    except ImageNotFoundException:
        raise ImageNotFoundException(find_image_error_variable)
    if image_data_array[0] is True:
        height = image_data_array[1][2] - image_data_array[1][0]
        width = image_data_array[1][3] - image_data_array[1][1]
        center = [int(height / 2), int(width / 2)]
        image_center_x = image_data_array[1][0] + center[0]
        image_center_y = image_data_array[1][1] + center[1]
        set_position(int(image_center_x), int(image_center_y))
        click_mouse(mouse_keycode)
        return [image_center_x, image_center_y]
    else:
        raise ImageNotFoundException(cant_find_image)
