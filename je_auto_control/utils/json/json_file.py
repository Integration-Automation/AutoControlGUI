import json
from pathlib import Path
from threading import Lock

from je_auto_control.utils.exception.exception_tags import cant_find_json_error
from je_auto_control.utils.exception.exception_tags import cant_save_json_error
from je_auto_control.utils.exception.exceptions import AutoControlJsonActionException

_lock = Lock()


def read_action_json(json_file_path: str) -> list:
    """
    use to read action file
    :param json_file_path json file's path to read
    """
    try:
        _lock.acquire()
        file_path = Path(json_file_path)
        if file_path.exists() and file_path.is_file():
            with open(json_file_path) as read_file:
                return json.loads(read_file.read())
    except AutoControlJsonActionException:
        raise AutoControlJsonActionException(cant_find_json_error)
    finally:
        _lock.release()


def write_action_json(json_save_path: str, action_json: list) -> None:
    """
    use to save action file
    :param json_save_path  json save path
    :param action_json the json str include action to write
    """
    try:
        _lock.acquire()
        with open(json_save_path, "w+") as file_to_write:
            file_to_write.write(json.dumps(action_json))
    except AutoControlJsonActionException:
        raise AutoControlJsonActionException(cant_save_json_error)
    finally:
        _lock.release()
