from typing import List

from PIL import ImageGrab
from je_open_cv import template_detection


def find_image(image, detect_threshold: float = 1, draw_image: bool = False) -> List[int]:
    """
    :param image which image we want to find on screen
    :param detect_threshold detect precision 0.0 ~ 1.0; 1 is absolute equal
    :param draw_image draw detect tag on return image
    """
    grab_image = ImageGrab.grab()
    return template_detection.find_object(image=grab_image, template=image,
                                          detect_threshold=detect_threshold, draw_image=draw_image)


def find_image_multi(image, detect_threshold: float = 1, draw_image: bool = False) -> List[List[int]]:
    """
    :param image which image we want to find on screen
    :param detect_threshold detect precision 0.0 ~ 1.0; 1 is absolute equal
    :param draw_image draw detect tag on return image
    """
    grab_image = ImageGrab.grab()
    return template_detection.find_multi_object(image=grab_image, template=image,
                                                detect_threshold=detect_threshold, draw_image=draw_image)
