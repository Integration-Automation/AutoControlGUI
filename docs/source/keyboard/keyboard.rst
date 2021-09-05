========================
AutoControlGUI Keyboard
========================

| Keyboard type

.. code-block:: python

    import time

    from je_auto_control import type_key
    from je_auto_control import keys_table

    """
    check keys
    """
    print(keys_table.keys())

    """
    Linux in every type and press then release need stop 0.01 time in my computer,i'm not sure it's right?

    example:
        type_key("T")
        time.sleep(0.01)
        type_key("E")
        time.sleep(0.01)
        type_key("S")
        time.sleep(0.01)
        type_key("T")
        time.sleep(0.01)

    or:
        press_key("T")
        release_key("T")
        time.sleep(0.01)
    """

    type_key("T")
    type_key("E")
    type_key("S")
    type_key("T")

| Keyboard key is press

.. code-block:: python

    import sys

    from je_auto_control import check_key_is_press
    from je_auto_control import press_key
    from je_auto_control import release_key

    try:
        """
        because os key_code not equal
        """
        while True:
            if sys.platform in ["win32", "cygwin", "msys"]:
                press_key("backspace")
                """
                linux key backspace
                """
                if check_key_is_press(22):
                    sys.exit(0)
            elif sys.platform in ["darwin"]:
                press_key("f5")
                """
                osx key F5
                """
                if check_key_is_press(0x60):
                    sys.exit(0)
            elif sys.platform in ["linux", "linux2"]:
                press_key("A")
                """
                windows key a or you can use check_key_is_press(ord("A"))
                """
                if check_key_is_press("A"):
                    sys.exit(0)
    except Exception:
        raise Exception
    finally:
        if sys.platform in ["win32", "cygwin", "msys"]:
            release_key("A")
        elif sys.platform in ["darwin"]:
            release_key("f5")
        elif sys.platform in ["linux", "linux2"]:
            release_key("backspace")



| Keyboard write

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
