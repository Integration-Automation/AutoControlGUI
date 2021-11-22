from multiprocessing import Process


def timeout(check_function, time: int):
    new_process = Process(target=check_function)
    new_process.start()
    new_process.join(timeout=time)
    new_process.terminate()
    if new_process.exitcode is None:
        return "timeout"
    else:
        return "success"
