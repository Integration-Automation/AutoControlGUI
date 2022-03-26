class TestRecord(object):

    def __init__(self, init_total_record: bool = False):
        self.init_total_record = init_total_record
        self.record_list = list()
        self.error_record_list = list()
        self.total_record_list = list()

    def clean_record(self):
        self.record_list = list()
        self.error_record_list = list()
        self.total_record_list = list()


test_record = TestRecord()


def record_total(function_name: str, local_param, program_exception: str = None):
    if not test_record.init_total_record:
        pass
    else:
        test_record.record_list.append([function_name, local_param, program_exception])
