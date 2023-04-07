Mouse
----

* This module is used for simulating mouse control.
* It provides functions for simulating clicks, setting positions, etc.

The following example is to obtain information about mouse clicks:
mouse_table contains all the available mouse buttons.

.. code-block:: python

    from je_auto_control import mouse_table

    print(mouse_table)

The following example is holding down the mouse button and releasing it after one second.

.. code-block:: python

    from time import sleep

    from je_auto_control import press_mouse, release_mouse

    press_mouse("mouse_right")
    sleep(1)
    release_mouse("mouse_right")

The following example is clicking and releasing the mouse.

.. code-block:: python

    from je_auto_control import click_mouse

    click_mouse("mouse_right")

The following example is to check the mouse position and change the mouse position.

.. code-block:: python

    from je_auto_control import get_mouse_position, set_mouse_position

    print(get_mouse_position())
    set_mouse_position(100, 100)

Here's an example where the mouse will scroll up after 3 seconds:

.. code-block:: python

    from time import sleep
    from je_auto_control import scroll

    sleep(3)

    scroll(100)