========================
AutoControl 鍵盤使用
========================

| 鍵盤按下按鍵
| type_key 將會按下跟放開按鍵 此範例會自動打出 TEST

.. code-block:: python

    import time

    from je_auto_control import type_key
    from je_auto_control import keys_table

    """
    check keys
    """
    print(keys_table.keys())
    type_key("T")
    type_key("E")
    type_key("S")
    type_key("T")

| 檢查按鍵是否按下
| check_key_is_press 函數將會檢查按鍵是否按下 並返回布林值
.. code-block:: python

    import sys

    from je_auto_control import check_key_is_press
    from je_auto_control import press_key
    from je_auto_control import release_key
    from je_auto_control import AutoControlException

    try:
        """
        because os key_code not equal
        """
        while True:
            if sys.platform in ["win32", "cygwin", "msys"]:
                press_key("A")
                """
                windows key a or you can use check_key_is_press(ord("A"))
                """
                if check_key_is_press("A"):
                    sys.exit(0)
            elif sys.platform in ["darwin"]:
                press_key("f5")
                """
                osx key F5
                """
                if check_key_is_press(0x60):
                    sys.exit(0)
            elif sys.platform in ["linux", "linux2"]:
                press_key("a")
                """
                linux key a
                """
                if check_key_is_press(0):
                    sys.exit(0)
    except AutoControlException:
        raise AutoControlException
    finally:
        if sys.platform in ["win32", "cygwin", "msys"]:
            release_key("A")
        elif sys.platform in ["darwin"]:
            release_key("f5")
        elif sys.platform in ["linux", "linux2"]:
            release_key("a")


| 鍵盤 write 函數
| write 函數將會自動按下與釋放所有傳入的字串

.. code-block:: python

    import sys

    from je_auto_control import keys_table
    from je_auto_control import press_key
    from je_auto_control import release_key
    from je_auto_control import write

    print(keys_table.keys())

    press_key("shift")
    write("123456789")
    press_key("return")
    release_key("return")
    write("abcdefghijklmnopqrstuvwxyz")
    release_key("shift")
    press_key("return")
    release_key("return")
    write("abcdefghijklmnopqrstuvwxyz")
    press_key("return")
    release_key("return")
    """
    this write will print one error -> keyboard write error can't find key : Ѓ and write remain string
    """
    write("Ѓ123456789")


| Keyboard hotkey

.. code-block:: python

    import sys

    from je_auto_control import hotkey

    if sys.platform in ["win32", "cygwin", "msys"]:
        hotkey(["lcontrol", "a"])
        hotkey(["lcontrol", "c"])
        hotkey(["lcontrol", "v"])
        hotkey(["lcontrol", "v"])

    elif sys.platform in ["darwin"]:
        hotkey(["command", "a"])
        hotkey(["command", "c"])
        hotkey(["command", "v"])
        hotkey(["command", "v"])

    elif sys.platform in ["linux", "linux2"]:
        hotkey(["ctrl", "a"])
        hotkey(["ctrl", "c"])
        hotkey(["ctrl", "v"])
        hotkey(["ctrl", "v"])
