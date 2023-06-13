import queue
import shlex
import subprocess
import sys
from threading import Thread

from je_auto_control.utils.logging.loggin_instance import auto_control_logger


class ShellManager(object):

    def __init__(
            self,
            shell_encoding: str = "utf-8",
            program_buffer: int = 10240000,
    ):
        """
        :param shell_encoding: shell command read output encoding
        :param program_buffer: buffer size
        """
        self.read_program_error_output_from_thread = None
        self.read_program_output_from_thread = None
        self.still_run_shell: bool = True
        self.process = None
        self.run_output_queue: queue = queue.Queue()
        self.run_error_queue: queue = queue.Queue()
        self.program_encoding: str = shell_encoding
        self.program_buffer: int = program_buffer

    def exec_shell(self, shell_command: [str, list]) -> None:
        """
        :param shell_command: shell command will run
        :return: if error return result and True else return result and False
        """
        auto_control_logger.info(f"exec_shell, shell_command: {shell_command}")
        try:
            self.exit_program()
            if sys.platform in ["win32", "cygwin", "msys"]:
                args = shell_command
            else:
                args = shlex.split(shell_command)
            self.process = subprocess.Popen(
                args=args,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                shell=True,
            )
            self.still_run_shell = True
            # program output message queue thread
            self.read_program_output_from_thread = Thread(
                target=self.read_program_output_from_process,
                daemon=True
            )
            self.read_program_output_from_thread.start()
            # program error message queue thread
            self.read_program_error_output_from_thread = Thread(
                target=self.read_program_error_output_from_process,
                daemon=True
            )
            self.read_program_error_output_from_thread.start()
        except Exception as error:
            auto_control_logger.error(
                f"exec_shell, shell_command: {shell_command}, failed: {repr(error)}")

    # tkinter_ui update method
    def pull_text(self) -> None:
        try:
            if not self.run_error_queue.empty():
                error_message = self.run_error_queue.get_nowait()
                error_message = str(error_message).strip()
                if error_message:
                    print(error_message, file=sys.stderr)
            if not self.run_output_queue.empty():
                output_message = self.run_output_queue.get_nowait()
                output_message = str(output_message).strip()
                if output_message:
                    print(output_message)
        except queue.Empty:
            pass
        if self.process.returncode == 0:
            self.exit_program()
        elif self.process.returncode is not None:
            self.exit_program()
        if self.still_run_shell:
            # poll return code
            self.process.poll()

    # exit program change run flag to false and clean read thread and queue and process
    def exit_program(self) -> None:
        self.still_run_shell = False
        if self.read_program_output_from_thread is not None:
            self.read_program_output_from_thread = None
        if self.read_program_error_output_from_thread is not None:
            self.read_program_error_output_from_thread = None
        self.print_and_clear_queue()
        if self.process is not None:
            self.process.terminate()
            print(f"Shell command exit with code {self.process.returncode}")
            self.process = None

    def print_and_clear_queue(self) -> None:
        try:
            for std_output in iter(self.run_output_queue.get_nowait, None):
                std_output = str(std_output).strip()
                if std_output:
                    print(std_output)
            for std_err in iter(self.run_error_queue.get_nowait, None):
                std_err = str(std_err).strip()
                if std_err:
                    print(std_err, file=sys.stderr)
        except queue.Empty:
            pass
        self.run_output_queue = queue.Queue()
        self.run_error_queue = queue.Queue()

    def read_program_output_from_process(self) -> None:
        while self.still_run_shell:
            program_output_data = self.process.stdout.raw.read(
                self.program_buffer) \
                .decode(self.program_encoding)
            self.run_output_queue.put_nowait(program_output_data)

    def read_program_error_output_from_process(self) -> None:
        while self.still_run_shell:
            program_error_output_data = self.process.stderr.raw.read(
                self.program_buffer) \
                .decode(self.program_encoding)
            self.run_error_queue.put_nowait(program_error_output_data)


default_shell_manager = ShellManager()
