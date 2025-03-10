鍵盤
----

* 用來模擬鍵盤的控制。
* 提供熱鍵、檢盤鍵盤按鍵狀態(是否按下)、模擬鍵盤控制等功能。

以下範例是取得鍵盤的資訊，
* special_table 是特定的鍵盤按鍵 ( 注意! 不是每個平台都有 )
* keys_table 是所有可以使用的按鍵

.. code-block:: python

    from je_auto_control import keys_table, get_special_table

    print(keys_table)
    print(get_special_table())


以下範例是按著鍵盤的傳入的按鍵，並在一秒後釋放

.. code-block:: python

    from time import sleep
    from je_auto_control import press_keyboard_key, release_keyboard_key

    press_key("a")
    sleep(1)
    release_key("a")

以下範例會幫你完成按下與釋放傳入的按鍵

.. code-block:: python

    from je_auto_control import type_keyboard

    type_keyboard("a")

以下範例是檢查鍵盤 a 鍵是否按著

.. code-block:: python

    from je_auto_control import check_key_is_press

    check_key_is_press("a")

以下範例是按下與放開一串按鍵

.. code-block:: python

    from je_auto_control import write

    write("abcdefg")

以下範例使用熱鍵，會按下傳入的按鍵並相反的放開

.. code-block:: python

    import sys

    from je_auto_control import hotkey

    if sys.platform in ["win32", "cygwin", "msys"]:
        hotkey(["lcontrol", "a", "lcontrol", "c", "lcontrol", "v", "lcontrol", "v"])

    elif sys.platform in ["darwin"]:
        hotkey(["command", "a", "command", "c", "command", "v", "command", "v"])

    elif sys.platform in ["linux", "linux2"]:
        hotkey(["ctrl", "a", "ctrl", "c", "ctrl", "v", "ctrl", "v"])