AutoControlGUI Keyboard Doc
==========================


.. code-block:: python

    def press_key(keycode: [int, str], is_shift: bool = False):
    """
    use to press a key still press to use release key
    or use critical exit
    return keycode
    :param keycode which keycode we want to press
    :param is_shift press shift True or False
    """

    def release_key(keycode: [int, str], is_shift: bool = False):
    """
    use to release pressed key return keycode
    :param keycode which keycode we want to release
    :param is_shift press shift True or False
    """

    def type_key(keycode: [int, str], is_shift: bool = False):
    """
    press and release key return keycode
    :param keycode which keycode we want to type
    :param is_shift press shift True or False
    """

    def check_key_is_press(keycode: [int, str]):
    """
    use to check key is press return True or False
    :param keycode check key is press or not
    """

    def write(write_string: str, is_shift: bool = False):
    """
    use to press and release whole we get this function str
    return all press and release str
    :param write_string while string not on write_string+1 type_key(string)
    :param is_shift press shift True or False
    """

    def hotkey(key_code_list: list, is_shift: bool = False):
    """
    use to press and release all key on key_code_list
    then reverse list press and release again
    return [press_str_list, release_str_list]
    :param key_code_list press and release all key on list and reverse
    :param is_shift press shift True or False
    """