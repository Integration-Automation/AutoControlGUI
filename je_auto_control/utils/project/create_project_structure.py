from pathlib import Path
from os import getcwd
from threading import Lock

from je_auto_control.utils.json.json_file import write_action_json
from je_auto_control.utils.project.template.template_executor import executor_template_1, \
    executor_template_2
from je_auto_control.utils.project.template.template_keyword import template_keyword_1, \
    template_keyword_2


def create_dir(dir_name: str) -> None:
    """
    :param dir_name: create dir use dir name
    :return: None
    """
    Path(dir_name).mkdir(
        parents=True,
        exist_ok=True
    )


def create_template(parent_name: str) -> None:
    keyword_dir_path = Path(getcwd() + "/" + parent_name + "/keyword")
    executor_dir_path = Path(getcwd() + "/" + parent_name + "/executor")
    lock = Lock()
    if keyword_dir_path.exists() and keyword_dir_path.is_dir():
        write_action_json(getcwd() + "/" + parent_name + "/keyword/keyword1.json", template_keyword_1)
        write_action_json(getcwd() + "/" + parent_name + "/keyword/keyword2.json", template_keyword_2)
    if executor_dir_path.exists() and keyword_dir_path.is_dir():
        lock.acquire()
        try:
            with open(getcwd() + "/" + parent_name + "/executor/executor_one_file.py", "w+") as file:
                file.write(
                    executor_template_1.replace(
                        "{temp}",
                        getcwd() + "/" + parent_name + "/keyword/keyword1.json"
                    )
                )
            with open(getcwd() + "/" + parent_name + "/executor/executor_folder.py", "w+") as file:
                file.write(
                    executor_template_2.replace(
                        "{temp}",
                        getcwd() + "/" + parent_name + "/keyword"
                    )
                )
        finally:
            lock.release()


def create_project_dir(parent_name: str) -> None:
    create_dir(getcwd() + "/" + parent_name + "/keyword")
    create_dir(getcwd() + "/" + parent_name + "/executor")
    create_template(parent_name)
