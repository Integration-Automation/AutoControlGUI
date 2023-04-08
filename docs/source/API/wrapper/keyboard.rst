Keyboard API
----

.. code-block:: python

    def get_special_table():
        return special_mouse_keys_table

.. code-block:: python

    def get_keyboard_keys_table():
        return keyboard_keys_table

.. code-block:: python

    def press_keyboard_key(keycode: [int, str], is_shift: bool = False, skip_record: bool = False) -> str:
        """
        use to press a key still press to use release key
        or use critical exit
        return keycode
        :param keycode which keycode we want to press
        :param is_shift press shift True or False
        :param skip_record skip record on record total list True or False
        """

.. code-block:: python

    def release_keyboard_key(keycode: [int, str], is_shift: bool = False, skip_record: bool = False) -> str:
        """
        use to release pressed key return keycode
        :param keycode which keycode we want to release
        :param is_shift press shift True or False
        :param skip_record skip record on record total list True or False
        """

.. code-block:: python

    def type_keyboard(keycode: [int, str], is_shift: bool = False, skip_record: bool = False) -> str:
        """
        press and release key return keycode
        :param keycode which keycode we want to type
        :param is_shift press shift True or False
        :param skip_record skip record on record total list True or False
        """

.. code-block:: python

    def check_key_is_press(keycode: [int, str]) -> bool:
        """
        use to check key is press return True or False
        :param keycode check key is press or not
        """