from pathlib import Path

from je_auto_control.utils.exception.exception_tags import can_not_find_file_error_message
from je_auto_control.utils.exception.exceptions import AutoControlException
from je_auto_control.utils.logging.logging_instance import autocontrol_logger
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
        process_manager = ShellManager()
        # Pass an argv list so the path is launched verbatim: a single string
        # is shlex-split by ShellManager, which mangles a path containing a
        # space ("C:\\Program Files\\...\\foo.exe") into the wrong argv.
        process_manager.exec_shell([str(exe_path_obj)])
        if process_manager.process is None:
            # exec_shell swallows launch failures (OSError) internally and
            # leaves process unset; surface it as the documented exception.
            autocontrol_logger.error(
                f"start_exe, exe_path: {exe_path_obj}, launch failed"
            )
            raise AutoControlException(f"Failed to execute {exe_path_obj}")
        autocontrol_logger.info(f"Successfully started executable: {exe_path_obj}")
    else:
        autocontrol_logger.error(
            f"start_exe, exe_path: {exe_path_obj}, failed: {can_not_find_file_error_message}"
        )
        raise AutoControlException(can_not_find_file_error_message)