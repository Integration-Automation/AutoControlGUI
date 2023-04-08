Mouse keys API
----

* Windows

.. code-block:: python

        mouse_keys_table = {
        "mouse_left": win32_mouse_left,
        "mouse_middle": win32_mouse_middle,
        "mouse_right": win32_mouse_right,
        "mouse_x1": win32_mouse_x1,
        "mouse_x2": win32_mouse_x2
    }

* Linux

.. code-block:: python

    mouse_keys_table = {
        "mouse_left": x11_linux_mouse_left,
        "mouse_middle": x11_linux_mouse_middle,
        "mouse_right": x11_linux_mouse_right
    }
    special_mouse_keys_table = {
        "scroll_up": x11_linux_scroll_direction_up,
        "scroll_down": x11_linux_scroll_direction_down,
        "scroll_left": x11_linux_scroll_direction_left,
        "scroll_right": x11_linux_scroll_direction_right
    }

* MacOS

.. code-block:: python

     mouse_keys_table = {
        "mouse_left": osx_mouse_left,
        "mouse_middle": osx_mouse_middle,
        "mouse_right": osx_mouse_right,
    }