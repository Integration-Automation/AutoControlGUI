from multiprocessing import Process
from typing import Callable

from je_auto_control.utils.exception.exception_tags import timeout_need_on_main_error_message
from je_auto_control.utils.exception.exceptions import AutoControlTimeoutException


def multiprocess_timeout(check_function: Callable[[], None], time: int) -> str:
    """
    Run a function in a separate process with timeout.
    在子行程中執行函式，並設定超時機制

    :param check_function: 要執行的函式 Function to run
    :param time: 超時秒數 Timeout in seconds
    :return: "success" 或 "timeout"
    :raises AutoControlTimeoutException: 當超時時拋出例外
    """
    new_process = Process(target=check_function)
    new_process.start()
    new_process.join(timeout=time)

    if new_process.exitcode is None:  # 尚未結束，表示超時
        new_process.terminate()
        raise AutoControlTimeoutException(timeout_need_on_main_error_message)
    else:
        return "success"