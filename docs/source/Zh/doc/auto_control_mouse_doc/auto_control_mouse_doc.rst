==========================
AutoControl 滑鼠控制 文件
==========================


.. code-block:: python

    def mouse_preprocess(mouse_keycode: [int, str], x: int, y: int):
        """
        滑鼠的前處理函數 使用者通常不會用到
        check mouse keycode is verified or not
        and then check current mouse position
        如果使用且沒有設定 x y 那就設定 x y 為目前位置
        if x or y is None set x, y is current position
        mouse_keycode 想使用的滑鼠按鍵
        :param mouse_keycode which mouse keycode we want to click
         滑鼠 x 座標
        :param x mouse click x position
        滑鼠 y 座標
        :param y mouse click y position
        """

    def position():
    """
    取得滑鼠目前 x y
    get mouse current position
    回傳目前 x y
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
    return mouse_keycode, x, y
    哪個按鍵想按下
    :param mouse_keycode which mouse keycode we want to press
    :param x mouse press x position
    :param y mouse press y position
    """

    def release_mouse(mouse_keycode: [int, str], x: int = None, y: int = None):
    """
    放開滑鼠按鍵 可選擇座標
    release mouse keycode on x, y
    回傳 mouse_keycode x y
    return mouse_keycode, x, y
    想釋放的按鍵
    :param mouse_keycode which mouse keycode we want to release
    滑鼠釋放的位置 x 座標
    :param x mouse release x position
    滑鼠釋放的位置 y 座標
    :param y mouse release y position
    """

    def click_mouse(mouse_keycode: [int, str], x: int = None, y: int = None):
    """
    點擊與放開滑鼠按鍵 可選擇座標
    press and release mouse keycode on x, y
    回傳 傳入 mouse_keycode, x, y
    return keycode, x, y
    想點擊的按鍵
    :param mouse_keycode which mouse keycode we want to click
    滑鼠點擊的位置 x 座標
    :param x mouse click x position
    滑鼠點擊的位置 y 座標
    :param y mouse click y position
    """

    def scroll(scroll_value: int, x: int = None, y: int = None, scroll_direction: str = "scroll_down"):
    """"
    滾動滑鼠滾輪
    :param scroll_value scroll count
    滑鼠滾動的位置 x 座標
    :param x mouse scroll x position
    滑鼠滾動的位置 y 座標
    :param y mouse scroll y position
    方向
    :param scroll_direction which direction we want
    scroll_direction = scroll_up : direction up
    scroll_direction = scroll_down : direction down
    scroll_direction = scroll_left : direction left
    scroll_direction = scroll_right : direction right
    """
