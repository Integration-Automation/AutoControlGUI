AutoControlGUI 測試紀錄 文件
==========================


.. code-block:: python

    """
    只是一個紀錄成功與失敗的列別 使用者可能不會用到
    just a data class use to record success and failure
    """
    class TestRecord(object):

        def __init__(self):
            self.record_list = list()
            self.error_record_list = list()

        def clean_record(self):
            self.record_list = list()
            self.error_record_list = list()


    test_record = TestRecord()

