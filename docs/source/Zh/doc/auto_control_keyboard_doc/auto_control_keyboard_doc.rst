AutoControl 鍵盤控制 文件
==========================


.. code-block:: python

    def press_key(keycode: [int, str], is_shift: bool = False):
    """
    按下鍵盤按鍵 keycode 或是 字串 回傳傳入的字串 傳入一個以上會引發錯誤
    use to press a key still press to use release key
    or use critical exit
    return keycode
    哪個按鍵想按下
    :param keycode which keycode we want to press
    是否按著 shift
    :param is_shift press shift True or False
    """

    def release_key(keycode: [int, str], is_shift: bool = False):
    """
    放開鍵盤按鍵 keycode 或是 字串 回傳傳入的字串 傳入一個以上會引發錯誤
    use to release pressed key return keycode
    哪個按鍵想放開
    :param keycode which keycode we want to release
    是否按著 shift
    :param is_shift press shift True or False
    """

    def type_key(keycode: [int, str], is_shift: bool = False):
    """
    按下跟放開鍵盤 (類似正常使用)
    press and release key return keycode
    哪個按鍵想點擊
    :param keycode which keycode we want to type
    是否按著 shift
    :param is_shift press shift True or False
    """

    def check_key_is_press(keycode: [int, str]):
    """
    檢查鍵盤按鍵是否按下
    use to check key is press return True or False
    要檢查的按鍵
    :param keycode check key is press or not
    """

    def write(write_string: str, is_shift: bool = False):
    """
    對每個傳入的字元進行 type_key (按下與釋放的動作)
    use to press and release whole we get this function str
    回傳有成功 type_key 的按鍵
    return all press and release str
    字串來遍歷執行 type_key
    :param write_string while string not on write_string+1 type_key(string)
    是否按著 shift
    :param is_shift press shift True or False
    """

    def hotkey(key_code_list: list, is_shift: bool = False):
    """
    對傳入的按鍵進行 press_key 並反著釋放
    use to press and release all key on key_code_list
    then reverse list press and release again
    回傳按下的 字串 以及釋放的字串
    return [press_str_list, release_str_list]
    list 包含想按下與釋放的 按鍵
    :param key_code_list press and release all key on list and reverse
    :param is_shift press shift True or False
    """