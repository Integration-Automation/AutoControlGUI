import json
import os
from pathlib import Path
from threading import Lock
from typing import List, Dict

from je_auto_control.utils.exception.exception_tags import cant_find_json_error_message, cant_save_json_error_message
from je_auto_control.utils.exception.exceptions import AutoControlJsonActionException

_lock = Lock()


def read_action_json(json_file_path: str) -> List[List[Dict[str, Dict[str, str]]]]:
    """
    Read action JSON file.
    讀取動作 JSON 檔案

    :param json_file_path: JSON 檔案路徑
    :return: JSON 內容 (list of list of dict)
    """
    with _lock:
        try:
            file_path = Path(json_file_path)
            if file_path.exists() and file_path.is_file():
                with open(json_file_path, encoding="utf-8") as read_file:
                    return json.load(read_file)
            raise AutoControlJsonActionException(cant_find_json_error_message)
        except (OSError, json.JSONDecodeError) as error:
            raise AutoControlJsonActionException(f"{cant_find_json_error_message}: {repr(error)}") from error


def write_action_json(json_save_path: str, action_json: list) -> None:
    """
    Write action JSON file.
    寫入動作 JSON 檔案

    :param json_save_path: JSON 檔案儲存路徑
    :param action_json: 要寫入的 JSON 資料
    """
    with _lock:
        try:
            with open(json_save_path, "w+", encoding="utf-8") as file_to_write:
                json.dump(action_json, file_to_write, indent=4, ensure_ascii=False)
        except (OSError, TypeError, ValueError) as error:
            raise AutoControlJsonActionException(f"{cant_save_json_error_message}: {repr(error)}") from error


def format_action_json(json_file_path: str, check: bool = False) -> bool:
    """
    Canonicalise an action JSON file's layout (4-space indent, UTF-8).
    標準化動作 JSON 檔案的排版

    :param json_file_path: JSON 檔案路徑
    :param check: 若為 True，只回報是否需要重新排版而不寫入
    :return: 內容是否改變 (或在 check 模式下是否將會改變)
    """
    real_path = os.path.realpath(json_file_path)
    actions = read_action_json(real_path)
    canonical = json.dumps(actions, indent=4, ensure_ascii=False)
    with open(real_path, encoding="utf-8") as read_file:
        current = read_file.read()
    changed = current.strip() != canonical.strip()
    if check or not changed:
        return changed
    write_action_json(real_path, actions)
    return True