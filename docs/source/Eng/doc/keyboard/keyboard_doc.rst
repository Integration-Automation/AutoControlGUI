Keyboard
----

* Used to simulate keyboard control.
* Provides functions such as hotkeys, checking keyboard key status (whether pressed), and simulating keyboard control.
* The following example is to obtain information about the keyboard.

* special_table is a table of special keyboard keys (Note! Not every platform has them).
* keys_table is a table of all available keys.

.. code-block:: python

    from je_auto_control import keys_table, get_special_table

    print(keys_table)
    print(get_special_table())


The following example presses a certain key on the keyboard and releases it after one second.

.. code-block:: python

    from time import sleep
    from je_auto_control import press_key, release_key

    press_key("a")
    sleep(1)
    release_key("a")

The following example presses and releases a key.

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

以下範例是按下按鍵並相反的釋放按鍵

.. code-block:: python

    import sys

    from je_auto_control import hotkey

    if sys.platform in ["win32", "cygwin", "msys"]:
        hotkey(["lcontrol", "a", "lcontrol", "c", "lcontrol", "v", "lcontrol", "v"])

    elif sys.platform in ["darwin"]:
        hotkey(["command", "a", "command", "c", "command", "v", "command", "v"])

    elif sys.platform in ["linux", "linux2"]:
        hotkey(["ctrl", "a", "ctrl", "c", "ctrl", "v", "ctrl", "v"])