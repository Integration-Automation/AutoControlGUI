========================
AutoControlGUI Mouse
========================

| Get location
| Set location
| Press and release mouse
| Click mouse
| Check mouse keys

.. code-block:: python

    import time

    from je_auto_control import position
    from je_auto_control import set_position
    from je_auto_control import press_mouse
    from je_auto_control import release_mouse
    from je_auto_control import click_mouse
    from je_auto_control import mouse_table

    time.sleep(1)

    print(position())
    set_position(809, 388)

    print(mouse_table.keys())

    press_mouse("mouse_right")
    release_mouse("mouse_right")
    press_mouse("mouse_left")
    release_mouse("mouse_left")
    click_mouse("mouse_left")

| Scroll mouse

.. code-block:: python

    from je_auto_control import scroll

    scroll(100)