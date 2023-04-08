Mouse API
----

.. code-block:: python

    def get_mouse_table():
        return mouse_keys_table

.. code-block:: python

    def mouse_preprocess(mouse_keycode: [int, str], x: int, y: int) -> Tuple[Union[int, str], int, int]:
        """
        check mouse keycode is verified or not
        and then check current mouse position
        if x or y is None set x, y is current position
        :param mouse_keycode which mouse keycode we want to click
        :param x mouse click x position
        :param y mouse click y position
        """

.. code-block:: python

    def get_mouse_position() -> Tuple[int, int]:
        """
        get mouse current position
        return mouse_x, mouse_y
        """

.. code-block:: python

    def set_mouse_position(x: int, y: int) -> Tuple[int, int]:
        """
        :param x set mouse position x
        :param y set mouse position y
        return x, y
        """

.. code-block:: python

    def press_mouse(mouse_keycode: [int, str], x: int = None, y: int = None) -> Tuple[Union[int, str], int, int]:
        """
        press mouse keycode on x, y
        return keycode, x, y
        :param mouse_keycode which mouse keycode we want to press
        :param x mouse click x position
        :param y mouse click y position
        """

.. code-block:: python

    def release_mouse(mouse_keycode: [int, str], x: int = None, y: int = None) -> Tuple[Union[int, str], int, int]:
        """
        release mouse keycode on x, y
        return keycode, x, y
        :param mouse_keycode which mouse keycode we want to release
        :param x mouse click x position
        :param y mouse click y position
        """

.. code-block:: python

    def click_mouse(mouse_keycode: [int, str], x: int = None, y: int = None) -> Tuple[Union[int, str], int, int]:
        """
        press and release mouse keycode on x, y
        return keycode, x, y
        :param mouse_keycode which mouse keycode we want to click
        :param x mouse click x position
        :param y mouse click y position
        """

.. code-block:: python

    def mouse_scroll(scroll_value: int, x: int = None, y: int = None, scroll_direction: str = "scroll_down") -> Tuple[int, str]:
        """"
        :param scroll_value scroll count
        :param x mouse click x position
        :param y mouse click y position
        :param scroll_direction which direction we want to scroll (only linux)
        scroll_direction = scroll_up : direction up
        scroll_direction = scroll_down : direction down
        scroll_direction = scroll_left : direction left
        scroll_direction = scroll_right : direction right
        """

