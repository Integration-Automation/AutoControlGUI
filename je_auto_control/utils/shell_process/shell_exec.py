import queue
import shlex
import subprocess
import sys
from threading import Thread
from typing import Union

from je_auto_control.utils.logging.loggin_instance import autocontrol_logger


class ShellManager:
    """
    ShellManager
    Shell 指令管理器
    - 執行外部 shell 指令
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

    def exec_shell(self, shell_command: Union[str, list]) -> None:
        """
        Execute shell command.
        執行 shell 指令
        """
        autocontrol_logger.info(f"exec_shell, shell_command: {shell_command}")
        try:
            self.exit_program()

            if sys.platform in ["win32", "cygwin", "msys"]:
                args = shell_command if isinstance(shell_command, str) else " ".join(shell_command)
                self.process = subprocess.Popen(
                    args,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    shell=True,
                )
            else:
                args = shlex.split(shell_command) if isinstance(shell_command, str) else shell_command
                self.process = subprocess.Popen(
                    args,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    shell=False,
                )

            self.still_run_shell = True

            # stdout thread
            self.read_program_output_from_thread = Thread(
                target=self._read_stream,
                args=(self.process.stdout, self.run_output_queue),
                daemon=True
            )
            self.read_program_output_from_thread.start()

            # stderr thread
            self.read_program_error_output_from_thread = Thread(
                target=self._read_stream,
                args=(self.process.stderr, self.run_error_queue),
                daemon=True
            )
            self.read_program_error_output_from_thread.start()

        except Exception as error:
            autocontrol_logger.error(f"exec_shell failed, shell_command: {shell_command}, error: {repr(error)}")

    def pull_text(self) -> None:
        """
        Pull text from queues and print.
        從 queue 取出訊息並輸出
        """
        try:
            while not self.run_error_queue.empty():
                error_message = self.run_error_queue.get_nowait().strip()
                if error_message:
                    print(error_message, file=sys.stderr)

            while not self.run_output_queue.empty():
                output_message = self.run_output_queue.get_nowait().strip()
                if output_message:
                    print(output_message)

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
            print(f"Shell command exit with code {self.process.returncode}")
            self.process = None

        self.print_and_clear_queue()

    def print_and_clear_queue(self) -> None:
        """
        Print and clear queues.
        輸出並清空 queue
        """
        while not self.run_output_queue.empty():
            print(self.run_output_queue.get_nowait().strip())

        while not self.run_error_queue.empty():
            print(self.run_error_queue.get_nowait().strip(), file=sys.stderr)

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


# 預設 ShellManager 實例 Default instance
default_shell_manager = ShellManager()