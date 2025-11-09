import json
from threading import Lock
from typing import Dict, Tuple

from je_auto_control.utils.exception.exception_tags import cant_generate_json_report_error_message
from je_auto_control.utils.exception.exceptions import AutoControlGenerateJsonReportException
from je_auto_control.utils.logging.loggin_instance import autocontrol_logger
from je_auto_control.utils.test_record.record_test_class import test_record_instance


def generate_json() -> Tuple[Dict[str, Dict[str, str]], Dict[str, Dict[str, str]]]:
    """
    Generate JSON data from test records.
    從測試紀錄生成 JSON 資料

    :return: (success_dict, failure_dict)
    """
    autocontrol_logger.info("generate_json")

    if not test_record_instance.test_record_list:
        raise AutoControlGenerateJsonReportException(cant_generate_json_report_error_message)

    success_dict: Dict[str, Dict[str, str]] = {}
    failure_dict: Dict[str, Dict[str, str]] = {}

    success_count, failure_count = 1, 1
    for record_data in test_record_instance.test_record_list:
        record_entry = {
            "function_name": str(record_data.get("function_name")),
            "param": str(record_data.get("local_param")),
            "time": str(record_data.get("time")),
            "exception": str(record_data.get("program_exception")),
        }
        if record_data.get("program_exception") == "None":
            success_dict[f"Success_Test{success_count}"] = record_entry
            success_count += 1
        else:
            failure_dict[f"Failure_Test{failure_count}"] = record_entry
            failure_count += 1

    return success_dict, failure_dict


def _write_json_file(file_name: str, data: Dict[str, Dict[str, str]], lock: Lock) -> None:
    """
    Write JSON data to file safely with lock.
    使用 Lock 安全地將 JSON 資料寫入檔案

    :param file_name: 檔案名稱
    :param data: 要寫入的 JSON 資料
    :param lock: 執行緒鎖
    """
    with lock:
        try:
            with open(file_name, "w+", encoding="utf-8") as file_to_write:
                json.dump(data, file_to_write, indent=4, ensure_ascii=False)
        except Exception as error:
            autocontrol_logger.error(f"Failed to write {file_name}, error: {repr(error)}")


def generate_json_report(json_file_name: str = "default_name") -> None:
    """
    Output JSON report files (success and failure).
    輸出 JSON 報告檔案 (成功與失敗)

    :param json_file_name: 檔案名稱前綴
    """
    autocontrol_logger.info(f"generate_json_report, json_file_name: {json_file_name}")

    success_dict, failure_dict = generate_json()
    lock = Lock()

    _write_json_file(json_file_name + "_success.json", success_dict, lock)
    _write_json_file(json_file_name + "_failure.json", failure_dict, lock)