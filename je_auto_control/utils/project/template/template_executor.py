executor_template_1: str = \
    """from je_auto_control import execute_action, read_action_json

execute_action(
    read_action_json(
        r"{temp}"
    )
)
"""

executor_template_2: str = \
    """from je_auto_control import execute_files, get_dir_files_as_list

execute_files(
    get_dir_files_as_list(
        r"{temp}"
    )
)
"""
