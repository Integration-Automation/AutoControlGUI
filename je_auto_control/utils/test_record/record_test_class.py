import datetime


class TestRecord(object):

    def __init__(self, init_record: bool = False):
        self.init_record: bool = init_record
        self.test_record_list: list = list()

    def clean_record(self) -> None:
        self.test_record_list = list()

    def set_record_enable(self, set_enable: bool = True):
        self.init_record = set_enable


test_record_instance = TestRecord()


def record_action_to_list(function_name: str, local_param, program_exception: str = None) -> None:
    if not test_record_instance.init_record:
        pass
    else:
        test_record_instance.test_record_list.append(
            {
                "function_name": function_name,
                "local_param": local_param,
                "time": str(datetime.datetime.now()),
                "program_exception": repr(program_exception)
            }
        )
