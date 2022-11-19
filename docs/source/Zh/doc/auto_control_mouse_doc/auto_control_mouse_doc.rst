AutoControl 滑鼠控制 文件
==========================


.. code-block:: python

    def mouse_preprocess(mouse_keycode: [int, str], x: int, y: int):
        """
        滑鼠的前處理函數 使用者通常不會用到
        check mouse keycode is verified or not
        and then check current mouse position
        if x or y is None set x, y is current position
        :param mouse_keycode which mouse keycode we want to click
        :param x mouse click x position
        :param y mouse click y position
        """

    def position():
    """
    取毒滑鼠目前 x y
    get mouse current position
    return mouse_x, mouse_y
    """

    def set_position(x: int, y: int):
    """
    設置滑鼠 x y
    :param x set mouse position x
    :param y set mouse position y
    return x, y
    """

    def press_mouse(mouse_keycode: [int, str], x: int = None, y: int = None):
    """
    按下滑鼠按鍵 可選擇座標
    press mouse keycode on x, y
    return keycode, x, y
    :param mouse_keycode which mouse keycode we want to press
    :param x mouse click x position
    :param y mouse click y position
    """

    def release_mouse(mouse_keycode: [int, str], x: int = None, y: int = None):
    """
    放開滑鼠按鍵 可選擇座標
    release mouse keycode on x, y
    return keycode, x, y
    :param mouse_keycode which mouse keycode we want to release
    :param x mouse click x position
    :param y mouse click y position
    """

    def click_mouse(mouse_keycode: [int, str], x: int = None, y: int = None):
    """
    點擊與放開滑鼠按鍵 可選擇座標
    press and release mouse keycode on x, y
    return keycode, x, y
    :param mouse_keycode which mouse keycode we want to click
    :param x mouse click x position
    :param y mouse click y position
    """

    def scroll(scroll_value: int, x: int = None, y: int = None, scroll_direction: str = "scroll_down"):
    """"
    滾動滑鼠滾輪
    :param scroll_value scroll count
    :param x mouse click x position
    :param y mouse click y position
    :param scroll_direction which direction we want
    scroll_direction = scroll_up : direction up
    scroll_direction = scroll_down : direction down
    scroll_direction = scroll_left : direction left
    scroll_direction = scroll_right : direction right
    """
