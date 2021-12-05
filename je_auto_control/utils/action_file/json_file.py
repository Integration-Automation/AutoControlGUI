import json
from pathlib import Path
from threading import Lock

from je_auto_control.utils.exception.exceptions import AutoControlJsonActionException
from je_auto_control.utils.exception.exception_tag import cant_save_json_error
from je_auto_control.utils.exception.exception_tag import cant_find_json_error

lock = Lock()


def read_action_json(json_file_path: str):
    """
    :param json_file_path json file's path to read
    """
    try:
        lock.acquire()
        file_path = Path(json_file_path)
        if file_path.exists() and file_path.is_file():
            with open(json_file_path) as read_file:
                return read_file.read()
    except AutoControlJsonActionException:
        raise AutoControlJsonActionException(cant_find_json_error)
    finally:
        lock.release()


def write_action_json(json_save_path: str, action_json: str):
    """
    :param json_save_path  json save path
    :param action_json the json str include action to write
    """
    try:
        lock.acquire()
        with open(json_save_path, "w+") as file_to_write:
            file_to_write.write(action_json)
    except AutoControlJsonActionException:
        raise AutoControlJsonActionException(cant_save_json_error)
    finally:
        lock.release()

