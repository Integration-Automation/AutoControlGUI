from typing import List
from PIL import ImageGrab
from je_open_cv import template_detection


def find_image(image, detect_threshold: float = 1.0, draw_image: bool = False) -> List[int]:
    """
    Find a single image on the screen using template detection.
    使用模板匹配在螢幕上尋找單一影像

    :param image: Template image 模板影像 (要尋找的影像)
    :param detect_threshold: Detection precision (0.0 ~ 1.0, 1.0 = 完全相同)
    :param draw_image: Whether to draw detection markers 是否在回傳影像上標記偵測結果
    :return: List[int] [x, y] 座標位置
    """
    # 擷取螢幕畫面 Capture screen
    grab_image = ImageGrab.grab()

    # 使用模板匹配 Find object
    return template_detection.find_object(
        image=grab_image,
        template=image,
        detect_threshold=detect_threshold,
        draw_image=draw_image
    )


def find_image_multi(image, detect_threshold: float = 1.0, draw_image: bool = False) -> List[List[int]]:
    """
    Find multiple occurrences of an image on the screen using template detection.
    使用模板匹配在螢幕上尋找多個影像

    :param image: Template image 模板影像 (要尋找的影像)
    :param detect_threshold: Detection precision (0.0 ~ 1.0, 1.0 = 完全相同)
    :param draw_image: Whether to draw detection markers 是否在回傳影像上標記偵測結果
    :return: List[List[int]] 多個座標位置 [[x1, y1], [x2, y2], ...]
    """
    # 擷取螢幕畫面 Capture screen
    grab_image = ImageGrab.grab()

    # 使用模板匹配 Find multiple objects
    return template_detection.find_multi_object(
        image=grab_image,
        template=image,
        detect_threshold=detect_threshold,
        draw_image=draw_image
    )