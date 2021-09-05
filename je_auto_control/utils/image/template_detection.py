from PIL import ImageGrab
from je_open_cv import template_detection


def find_image(image, detect_threshold=1, draw_image=False):
    grab_image = ImageGrab.grab()
    return template_detection.find_object(image=grab_image, template=image,
                                          detect_threshold=detect_threshold, draw_image=draw_image)


def find_image_multi(image, detect_threshold=1, draw_image=False):
    grab_image = ImageGrab.grab()
    return template_detection.find_multi_object(image=grab_image, template=image,
                                                detect_threshold=detect_threshold, draw_image=draw_image)
