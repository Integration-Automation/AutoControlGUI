from pathlib import Path


def create_dir(dir_name: str):
    """
    :param dir_name: create dir use dir name
    :return: None
    """
    Path(dir_name).mkdir(
        parents=True,
        exist_ok=True
    )


def create_template_dir():
    create_dir("auto_control/template")
