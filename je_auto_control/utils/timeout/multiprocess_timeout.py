from multiprocessing import Process

from je_auto_control.utils.exception.exception_tags import timeout_need_on_main_error
from je_auto_control.utils.exception.exceptions import AutoControlTimeoutException


def multiprocess_timeout(check_function, time: int):
    try:
        new_process: Process = Process(target=check_function)
        new_process.start()
        new_process.join(timeout=time)
    except AutoControlTimeoutException:
        raise AutoControlTimeoutException(timeout_need_on_main_error)
    new_process.terminate()
    if new_process.exitcode is None:
        return "timeout"
    else:
        return "success"
