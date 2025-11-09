from pathlib import Path

from je_auto_control.utils.exception.exception_tags import can_not_find_file_error_message
from je_auto_control.utils.exception.exceptions import AutoControlException
from je_auto_control.utils.logging.loggin_instance import autocontrol_logger
from je_auto_control.utils.shell_process.shell_exec import ShellManager


def start_exe(exe_path: str) -> None:
    """
    Start an external executable file.
    啟動外部可執行檔

    :param exe_path: 可執行檔路徑 Path to executable file
    :raises AutoControlException: 當檔案不存在或不是檔案時拋出例外
    """
    autocontrol_logger.info(f"start_exe, exe_path: {exe_path}")

    exe_path_obj = Path(exe_path)

    if exe_path_obj.exists() and exe_path_obj.is_file():
        try:
            process_manager = ShellManager()
            process_manager.exec_shell(str(exe_path_obj))
            autocontrol_logger.info(f"Successfully started executable: {exe_path_obj}")
        except Exception as error:
            autocontrol_logger.error(
                f"start_exe, exe_path: {exe_path_obj}, exec_shell failed: {repr(error)}"
            )
            raise AutoControlException(f"Failed to execute {exe_path_obj}: {repr(error)}")
    else:
        autocontrol_logger.error(
            f"start_exe, exe_path: {exe_path_obj}, failed: {AutoControlException(can_not_find_file_error_message)}"
        )
        raise AutoControlException(can_not_find_file_error_message)