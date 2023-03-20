import json
import sys
from threading import Lock

from je_auto_control.utils.exception.exception_tags import cant_generate_json_report
from je_auto_control.utils.exception.exceptions import AutoControlGenerateJsonReportException
from je_auto_control.utils.test_record.record_test_class import test_record_instance


def generate_json():
    if len(test_record_instance.test_record_list) == 0:
        raise AutoControlGenerateJsonReportException(cant_generate_json_report)
    else:
        success_dict = dict()
        failure_dict = dict()
        failure_count: int = 1
        failure_test_str: str = "Failure_Test"
        success_count: int = 1
        success_test_str: str = "Success_Test"
        for record_data in test_record_instance.test_record_list:
            if record_data.get("program_exception") == "None":
                success_dict.update(
                    {
                        success_test_str + str(success_count): {
                            "function_name": str(record_data.get("function_name")),
                            "param": str(record_data.get("local_param")),
                            "time": str(record_data.get("time")),
                            "exception": str(record_data.get("program_exception"))
                        }
                    }
                )
                success_count = success_count + 1
            else:
                failure_dict.update(
                    {
                        failure_test_str + str(failure_count): {
                            "function_name": str(record_data.get("function_name")),
                            "param": str(record_data.get("local_param")),
                            "time": str(record_data.get("time")),
                            "exception": str(record_data.get("program_exception"))
                        }
                    }
                )
                failure_count = failure_count + 1
    return success_dict, failure_dict


def generate_json_report(json_file_name: str = "default_name"):
    """
    :param json_file_name: save json file's name
    :return:
    """
    lock = Lock()
    success_dict, failure_dict = generate_json()
    try:
        lock.acquire()
        with open(json_file_name + "_success.json", "w+") as file_to_write:
            json.dump(dict(success_dict), file_to_write, indent=4)
    except Exception as error:
        print(repr(error), file=sys.stderr)
    finally:
        lock.release()
    try:
        lock.acquire()
        with open(json_file_name + "_failure.json", "w+") as file_to_write:
            json.dump(dict(failure_dict), file_to_write, indent=4)
    except Exception as error:
        print(repr(error), file=sys.stderr)
    finally:
        lock.release()
