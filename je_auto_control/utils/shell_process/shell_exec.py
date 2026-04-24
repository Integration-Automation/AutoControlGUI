import queue
import shlex
import subprocess  # nosec B404  # reason: ShellManager intentionally invokes user-supplied subprocesses without shell
import sys
from threading import Thread
from typing import List, Union

from je_auto_control.utils.logging.logging_instance import autocontrol_logger


def _normalize_command(shell_command: Union[str, List[str]]) -> List[str]:
    """
    Normalize shell command to an argv list with no shell interpretation.
    將 shell 指令正規化為 argv list，不經 shell 解譯，避免指令注入。
    """
    if isinstance(shell_command, list):
        return [str(part) for part in shell_command]
    posix_mode = sys.platform not in ("win32", "cygwin", "msys")
    return shlex.split(shell_command, posix=posix_mode)


class ShellManager:
    """
    ShellManager
    Shell 指令管理器
    - 執行外部 shell 指令 (不使用 shell=True，避免注入)
    - 使用背景執行緒持續讀取 stdout / stderr
    - 將輸出放入 queue，供 pull_text() 取出
    """

    def __init__(self, shell_encoding: str = "utf-8", program_buffer: int = 10240000):
        """
        :param shell_encoding: shell command read output encoding
        :param program_buffer: buffer size
        """
        self.read_program_error_output_from_thread: Union[Thread, None] = None
        self.read_program_output_from_thread: Union[Thread, None] = None
        self.still_run_shell: bool = False
        self.process: Union[subprocess.Popen, None] = None
        self.run_output_queue: queue.Queue = queue.Queue()
        self.run_error_queue: queue.Queue = queue.Queue()
        self.program_encoding: str = shell_encoding
        self.program_buffer: int = program_buffer

    def exec_shell(self, shell_command: Union[str, List[str]]) -> None:
        """
        Execute shell command with shell=False.
        執行 shell 指令 (shell=False，呼叫端需自備 argv 或可被 shlex 切分的字串)
        """
        autocontrol_logger.info(f"exec_shell, shell_command: {shell_command}")
        try:
            self.exit_program()
            args = _normalize_command(shell_command)
            # nosemgrep: python.lang.security.audit.dangerous-subprocess-use-audit.dangerous-subprocess-use-audit
            self.process = subprocess.Popen(  # nosec B603  # reason: shell=False, argv list validated via _normalize_command
                args,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                shell=False,
            )

            self.still_run_shell = True

            self.read_program_output_from_thread = Thread(
                target=self._read_stream,
                args=(self.process.stdout, self.run_output_queue),
                daemon=True,
            )
            self.read_program_output_from_thread.start()

            self.read_program_error_output_from_thread = Thread(
                target=self._read_stream,
                args=(self.process.stderr, self.run_error_queue),
                daemon=True,
            )
            self.read_program_error_output_from_thread.start()

        except (OSError, ValueError) as error:
            autocontrol_logger.error(
                f"exec_shell failed, shell_command: {shell_command}, error: {repr(error)}"
            )

    def pull_text(self) -> None:
        """
        Pull text from queues and log.
        從 queue 取出訊息並透過 logger 輸出
        """
        try:
            while not self.run_error_queue.empty():
                error_message = self.run_error_queue.get_nowait().strip()
                if error_message:
                    autocontrol_logger.error(error_message)

            while not self.run_output_queue.empty():
                output_message = self.run_output_queue.get_nowait().strip()
                if output_message:
                    autocontrol_logger.info(output_message)

        except queue.Empty:
            pass

        if self.process and self.process.poll() is not None:
            self.exit_program()

    def exit_program(self) -> None:
        """
        Exit program and clean resources.
        結束程式並清理資源
        """
        self.still_run_shell = False

        if self.process is not None:
            self.process.terminate()
            autocontrol_logger.info(
                f"Shell command exit with code {self.process.returncode}"
            )
            self.process = None

        self.log_and_clear_queue()

    def log_and_clear_queue(self) -> None:
        """
        Log and clear queues.
        透過 logger 輸出並清空 queue
        """
        while not self.run_output_queue.empty():
            autocontrol_logger.info(self.run_output_queue.get_nowait().strip())

        while not self.run_error_queue.empty():
            autocontrol_logger.error(self.run_error_queue.get_nowait().strip())

        self.run_output_queue = queue.Queue()
        self.run_error_queue = queue.Queue()

    def _read_stream(self, stream, target_queue: queue.Queue) -> None:
        """
        Read stream line by line and put into queue.
        讀取輸出流並放入 queue
        """
        while self.still_run_shell and stream:
            line = stream.readline(self.program_buffer)
            if not line:
                break
            target_queue.put_nowait(line.decode(self.program_encoding, "replace"))


default_shell_manager = ShellManager()
