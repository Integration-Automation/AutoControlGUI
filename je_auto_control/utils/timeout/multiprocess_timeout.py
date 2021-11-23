from multiprocessing import Process
from je_auto_control.utils.je_auto_control_exception.exceptions import AutoControlTimeoutException
from je_auto_control.utils.je_auto_control_exception.exception_tag import timeout_need_on_main_error


def multiprocess_timeout(check_function, time: int):
    try:
        new_process = Process(target=check_function)
        new_process.start()
        new_process.join(timeout=time)
    except AutoControlTimeoutException:
        raise AutoControlTimeoutException(timeout_need_on_main_error)
    new_process.terminate()
    if new_process.exitcode is None:
        return "timeout"
    else:
        return "success"
