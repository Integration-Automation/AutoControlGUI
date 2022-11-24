====================================================
AutoControl 螢幕操作 文件
====================================================


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
        存檔路徑
        :param file_path screenshot file save path
        截圖區域
        :param region screenshot region
        """
