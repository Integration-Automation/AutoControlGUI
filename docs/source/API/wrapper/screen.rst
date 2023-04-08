Screen API
----

.. code-block:: python

    def screen_size() -> Tuple[int, int]:
        """
        get screen size
        """

.. code-block:: python

    def screenshot(file_path: str = None, screen_region: list = None) -> List[int]:
        """
        use to capture current screen image
        :param file_path screenshot file save path
        :param screen_region screenshot screen_region
        """