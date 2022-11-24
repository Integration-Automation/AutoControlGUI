====================================================
AutoControl 圖片處理 文件
====================================================

.. code-block:: python

    def locate_all_image(image, detect_threshold: [float, int] = 1, draw_image: bool = False, **kwargs):
    """
    定位所有一樣的圖片 並回傳所有圖片的 list
    use to locate all image that detected and then return detected images list
    給予圖片路徑或者給予 PIL 的 ImageGrab.grab()
    :param image which image we want to find on screen (png or PIL ImageGrab.grab())
    偵測辨別度 0.0 ~ 1.0 1.0 是絕對相同
    :param detect_threshold detect precision 0.0 ~ 1.0; 1 is absolute equal (float or int)
    是否劃出偵測到圖片的範圍
    :param draw_image draw detect tag on return image (bool)
    """

    def locate_image_center(image, detect_threshold: [float, int] = 1, draw_image: bool = False, **kwargs):
    """
    定位圖片並取得其中心點
    use to locate image and return image center position
    給予圖片路徑或者給予 PIL 的 ImageGrab.grab()
    :param image which image we want to find on screen (png or PIL ImageGrab.grab())
    偵測辨別度 0.0 ~ 1.0 1.0 是絕對相同
    :param detect_threshold detect precision 0.0 ~ 1.0; 1 is absolute equal (float or int)
    是否劃出偵測到圖片的範圍
    :param draw_image draw detect tag on return image (bool)
    """

    def locate_and_click(image, mouse_keycode: [int, str], detect_threshold: [float, int] = 1, draw_image: bool = False, **kwargs):
    """
    定位圖片並點擊其中心點
    use to locate image and click image center position and the return image center position
    :param image which image we want to find on screen (png or PIL ImageGrab.grab())
    :param mouse_keycode which mouse keycode we want to click
    :param detect_threshold detect precision 0.0 ~ 1.0; 1 is absolute equal (float or int)
    :param draw_image draw detect tag on return image (bool)
    """

    def screenshot(file_path: str = None, region: list = None):
    """
    截圖並存檔 可指定範圍
    use to get now screen image return image
    存檔路徑
    :param file_path save screenshot path (None is no save)
    截圖範圍
    :param region screenshot region (screenshot region on screen)
    """

