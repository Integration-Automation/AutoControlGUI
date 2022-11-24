AutoControl Test Record Doc
==========================


.. code-block:: python

    """
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

