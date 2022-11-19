AutoControl 螢幕操作 文件
==========================


.. code-block:: python

    def size():
        """
        取得目前螢幕 pixel 大小
        get screen size
        """

    def screenshot(file_path: str = None, region: list = None):
        """
        截圖 可選擇截圖區域
        use to capture current screen image
        :param file_path screenshot file save path
        :param region screenshot region
        """
