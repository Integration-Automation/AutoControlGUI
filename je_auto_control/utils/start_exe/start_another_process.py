from pathlib import Path

from je_auto_control.utils.exception.exception_tags import can_not_find_file
from je_auto_control.utils.exception.exceptions import AutoControlException
from je_auto_control.utils.logging.loggin_instance import autocontrol_logger
from je_auto_control.utils.shell_process.shell_exec import ShellManager


def start_exe(exe_path: str) -> None:
    autocontrol_logger.info(f"start_another_process.py start_exe, exe_path: {exe_path}")
    exe_path = Path(exe_path)
    if exe_path.exists() and exe_path.is_file():
        process_manager = ShellManager()
        process_manager.exec_shell(str(exe_path))
    else:
        autocontrol_logger.error(
            f"start_exe, exe_path: {exe_path}, failed: {AutoControlException(can_not_find_file)}")
        raise AutoControlException(can_not_find_file)
