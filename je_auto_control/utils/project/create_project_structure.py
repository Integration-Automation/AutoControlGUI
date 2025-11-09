from os import getcwd
from pathlib import Path
from threading import Lock

from je_auto_control.utils.json.json_file import write_action_json
from je_auto_control.utils.logging.loggin_instance import autocontrol_logger
from je_auto_control.utils.project.template.template_executor import (
    executor_template_1, executor_template_2, bad_executor_template_1
)
from je_auto_control.utils.project.template.template_keyword import (
    template_keyword_1, template_keyword_2, bad_template_1
)


def create_dir(dir_name: str) -> None:
    """
    Create directory if not exists.
    建立目錄 (若不存在則建立)

    :param dir_name: 目錄名稱 Directory name
    """
    Path(dir_name).mkdir(parents=True, exist_ok=True)


def _write_file(file_path: Path, content: str) -> None:
    """
    Write content to file.
    將內容寫入檔案

    :param file_path: 檔案路徑 File path
    :param content: 要寫入的內容 Content to write
    """
    with open(file_path, "w+", encoding="utf-8") as file:
        file.write(content)


def create_template(parent_name: str, project_path: str = None) -> None:
    """
    Create template files in keyword and executor directories.
    在 keyword 與 executor 目錄中建立範例模板檔案

    :param parent_name: 專案主目錄名稱 Project parent directory name
    :param project_path: 專案路徑 Project path (預設為當前工作目錄)
    """
    if project_path is None:
        project_path = getcwd()

    keyword_dir_path = Path(project_path) / parent_name / "keyword"
    executor_dir_path = Path(project_path) / parent_name / "executor"
    lock = Lock()

    # 建立 keyword JSON 檔案 Create keyword JSON files
    if keyword_dir_path.exists() and keyword_dir_path.is_dir():
        write_action_json(str(keyword_dir_path) + "keyword1.json", template_keyword_1)
        write_action_json(str(keyword_dir_path) + "keyword2.json", template_keyword_2)
        write_action_json(str(keyword_dir_path) + "bad_keyword_1.json", bad_template_1)

    # 建立 executor Python 檔案 Create executor Python files
    if executor_dir_path.exists() and executor_dir_path.is_dir():
        with lock:
            _write_file(
                executor_dir_path / "executor_one_file.py",
                executor_template_1.replace("{temp}", str(keyword_dir_path / "keyword1.json"))
            )
            _write_file(
                executor_dir_path / "executor_bad_file.py",
                bad_executor_template_1.replace("{temp}", str(keyword_dir_path / "bad_keyword_1.json"))
            )
            _write_file(
                executor_dir_path / "executor_folder.py",
                executor_template_2.replace("{temp}", str(keyword_dir_path))
            )


def create_project_dir(project_path: str = None, parent_name: str = "AutoControl") -> None:
    """
    Create project directory structure and templates.
    建立專案目錄結構並生成範例模板檔案

    :param project_path: 專案路徑 Project path (預設為當前工作目錄)
    :param parent_name: 專案主目錄名稱 Project parent directory name
    """
    autocontrol_logger.info(f"create_project_dir, project_path: {project_path}, parent_name: {parent_name}")

    if project_path is None:
        project_path = getcwd()

    # 建立 keyword 與 executor 子目錄 Create keyword and executor subdirectories
    create_dir(str(Path(project_path)) + parent_name + "keyword")
    create_dir(str(Path(project_path)) + parent_name + "executor")

    # 建立範例模板檔案 Create template files
    create_template(parent_name, project_path)