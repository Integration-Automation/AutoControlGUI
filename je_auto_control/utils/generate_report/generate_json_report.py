import json
from typing import Dict, Tuple

from je_auto_control.utils.exception.exception_tags import cant_generate_json_report_error_message
from je_auto_control.utils.exception.exceptions import AutoControlGenerateJsonReportException
from je_auto_control.utils.json_store.json_store import atomic_write_text
from je_auto_control.utils.logging.logging_instance import autocontrol_logger
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


def _write_json_file(file_name: str, data: Dict[str, Dict[str, str]]) -> None:
    """Write ``data`` atomically; raise on failure instead of only logging it."""
    try:
        atomic_write_text(file_name, json.dumps(data, indent=4, ensure_ascii=False))
    except (OSError, TypeError, ValueError) as error:
        raise AutoControlGenerateJsonReportException(
            f"cannot write report {file_name!r}: {error!r}") from error


def generate_json_report(json_file_name: str = "default_name") -> None:
    """
    Output JSON report files (success and failure).
    輸出 JSON 報告檔案 (成功與失敗)

    :param json_file_name: 檔案名稱前綴
    """
    autocontrol_logger.info(f"generate_json_report, json_file_name: {json_file_name}")

    success_dict, failure_dict = generate_json()
    _write_json_file(json_file_name + "_success.json", success_dict)
    _write_json_file(json_file_name + "_failure.json", failure_dict)
