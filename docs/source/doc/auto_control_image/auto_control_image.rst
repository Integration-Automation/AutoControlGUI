AutoControlGUI Critical Exit
==========================

.. code-block:: python

    def locate_all_image(image, detect_threshold: [float, int] = 1, draw_image: bool = False, **kwargs):
    """
     use to locate all image that detected and then return detected images list
    :param image which image we want to find on screen (png or PIL ImageGrab.grab())
    :param detect_threshold detect precision 0.0 ~ 1.0; 1 is absolute equal (float or int)
    :param draw_image draw detect tag on return image (bool)
    """

    def locate_image_center(image, detect_threshold: [float, int] = 1, draw_image: bool = False, **kwargs):
    """
    use to locate image and return image center position
    :param image which image we want to find on screen (png or PIL ImageGrab.grab())
    :param detect_threshold detect precision 0.0 ~ 1.0; 1 is absolute equal (float or int)
    :param draw_image draw detect tag on return image (bool)
    """

    def locate_and_click(image, mouse_keycode: [int, str], detect_threshold: [float, int] = 1, draw_image: bool = False, **kwargs):
    """
    use to locate image and click image center position and the return image center position
    :param image which image we want to find on screen (png or PIL ImageGrab.grab())
    :param mouse_keycode which mouse keycode we want to click
    :param detect_threshold detect precision 0.0 ~ 1.0; 1 is absolute equal (float or int)
    :param draw_image draw detect tag on return image (bool)
    """

    def screenshot(file_path: str = None, region: list = None):
    """
    use to get now screen image return image
    :param file_path save screenshot path (None is no save)
    :param region screenshot region (screenshot region on screen)
    """

