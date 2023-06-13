from os import getcwd
from pathlib import Path
from threading import Lock

from je_auto_control.utils.json.json_file import write_action_json
from je_auto_control.utils.logging.loggin_instance import auto_control_logger
from je_auto_control.utils.project.template.template_executor import executor_template_1, \
    executor_template_2, bad_executor_template_1
from je_auto_control.utils.project.template.template_keyword import template_keyword_1, \
    template_keyword_2, bad_template_1


def create_dir(dir_name: str) -> None:
    """
    :param dir_name: create dir use dir name
    :return: None
    """
    Path(dir_name).mkdir(
        parents=True,
        exist_ok=True
    )


def create_template(parent_name: str, project_path: str = None) -> None:
    if project_path is None:
        project_path = getcwd()
    keyword_dir_path = Path(project_path + "/" + parent_name + "/keyword")
    executor_dir_path = Path(project_path + "/" + parent_name + "/executor")
    lock = Lock()
    if keyword_dir_path.exists() and keyword_dir_path.is_dir():
        write_action_json(project_path + "/" + parent_name + "/keyword/keyword1.json", template_keyword_1)
        write_action_json(project_path + "/" + parent_name + "/keyword/keyword2.json", template_keyword_2)
        write_action_json(project_path + "/" + parent_name + "/keyword/bad_keyword_1.json", bad_template_1)
    if executor_dir_path.exists() and keyword_dir_path.is_dir():
        lock.acquire()
        try:
            with open(project_path + "/" + parent_name + "/executor/executor_one_file.py", "w+") as file:
                file.write(
                    executor_template_1.replace(
                        "{temp}",
                        project_path + "/" + parent_name + "/keyword/keyword1.json"
                    )
                )
            with open(project_path + "/" + parent_name + "/executor/executor_bad_file.py", "w+") as file:
                file.write(
                    bad_executor_template_1.replace(
                        "{temp}",
                        project_path + "/" + parent_name + "/keyword/bad_keyword_1.json"
                    )
                )
            with open(project_path + "/" + parent_name + "/executor/executor_folder.py", "w+") as file:
                file.write(
                    executor_template_2.replace(
                        "{temp}",
                        project_path + "/" + parent_name + "/keyword"
                    )
                )
        finally:
            lock.release()


def create_project_dir(project_path: str = None, parent_name: str = "AutoControl") -> None:
    auto_control_logger.info(f"create_project_dir, project_path: {project_path}, parent_name: {parent_name}")
    if project_path is None:
        project_path = getcwd()
    create_dir(project_path + "/" + parent_name + "/keyword")
    create_dir(project_path + "/" + parent_name + "/executor")
    create_template(parent_name)
