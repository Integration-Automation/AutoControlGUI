import locale
import os
import queue
import shlex
import signal
import subprocess  # nosec B404  # reason: ShellManager intentionally invokes user-supplied subprocesses without shell
import sys
from threading import Thread
from typing import List, Optional, Union

from je_auto_control.utils.exception.exceptions import AutoControlActionException
from je_auto_control.utils.logging.logging_instance import autocontrol_logger


def console_encoding() -> str:
    """The encoding a console program writes in: on Windows the ANSI code page.

    ``locale.getpreferredencoding(False)`` answers ``utf-8`` in UTF-8 mode,
    which Python 3.15 turns on by default (PEP 686), while ``cmd``, ``sc`` or
    ``ipconfig`` keep writing the code page (cp950 on Traditional Chinese
    Windows), so their output came back as replacement characters.
    ``locale.getencoding`` (3.11+) ignores UTF-8 mode. Elsewhere the preferred
    encoding stays: a UTF-8 locale gives the same answer either way.
    """
    getencoding = getattr(locale, "getencoding", None)
    if sys.platform == "win32" and getencoding is not None:
        return getencoding()
    return locale.getpreferredencoding(False)


def command_args(shell_command: Union[str, List[str]]) -> Union[str, List[str]]:
    """What to hand ``subprocess`` for ``shell_command``, never through a shell.

    A list is the argv. A string is split with POSIX rules, except on
    native Windows (not Cygwin or MSYS, whose ``subprocess`` is POSIX), where
    it goes to ``CreateProcess`` as the command line it is:
    ``shlex`` in non-POSIX mode keeps the quote characters in each token, and
    ``subprocess`` then quoted them again -- ``"C:\\Program Files\\x"`` arrived
    with its quotes and a quoted executable path was not found.
    """
    if isinstance(shell_command, list):
        return [str(part) for part in shell_command]
    if sys.platform == "win32":
        return str(shell_command)
    return shlex.split(shell_command)


_BATCH_SUFFIXES = (".bat", ".cmd")
_CMD_METACHARACTERS = frozenset('&|<>^%!"\r\n')


def refuse_batch_metacharacters(args: Union[str, List[str]]) -> None:
    """Refuse an argv list for a .bat / .cmd file whose arguments hold cmd syntax.

    Windows runs a batch file through cmd.exe, which parses the command line
    again: ``subprocess`` quotes each argument for CreateProcess but not for
    cmd, so ``["run.bat", "x&calc"]`` also started calc. A string command is
    the caller's own command line and is left alone.
    """
    if sys.platform != "win32" or not isinstance(args, list) or not args:
        return
    if not args[0].lower().endswith(_BATCH_SUFFIXES):
        return
    for arg in args[1:]:
        if _CMD_METACHARACTERS.intersection(arg):
            raise ValueError(f"batch file argument {arg!r} contains cmd metacharacters")


def program_of(shell_command: Union[str, List[str], None]) -> str:
    """The program a command runs, which is all of it that may be logged.

    The arguments can hold a ``${secrets.*}`` value already filled in, and
    the whole command used to be logged, and written to the log file.
    """
    if isinstance(shell_command, list):
        return str(shell_command[0]) if shell_command else ""
    text = str(shell_command or "").strip()
    if text.startswith('"'):
        return text[1:].split('"', 1)[0]
    return text.split(" ", 1)[0]


def _taskkill_path() -> str:
    return os.path.join(os.environ.get("SystemRoot", r"C:\Windows"), "System32", "taskkill.exe")


def _kill_tree(process: subprocess.Popen) -> None:
    """Kill ``process`` and everything it started."""
    if sys.platform == "win32":
        taskkill = [_taskkill_path(), "/T", "/F", "/PID", str(process.pid)]
        subprocess.run(taskkill, capture_output=True, timeout=10, check=False)  # nosec B603  # nosemgrep  # reason: fixed system tool, our child's pid
    else:
        try:
            os.killpg(process.pid, signal.SIGKILL)
        except (ProcessLookupError, PermissionError):
            pass
    try:
        process.kill()
    except OSError:
        pass


def run_captured(argv: Union[str, List[str]], timeout_s: float,
                 input_bytes: Optional[bytes] = None) -> subprocess.CompletedProcess:
    """Run ``argv`` (no shell), capturing stdout and stderr as bytes, for at most ``timeout_s``.

    ``subprocess.run(timeout=...)`` kills only the program itself and then
    waits, without a limit, for everything still holding its pipes: a
    program that started one of its own (``cmd /c ping -n 9 ...`` took 8 s
    with a 1 s timeout) held the caller until it ended. On timeout the
    whole process tree is killed, then ``TimeoutExpired`` is raised.
    """
    # nosemgrep: python.lang.security.audit.dangerous-subprocess-use-audit.dangerous-subprocess-use-audit
    process = subprocess.Popen(argv, stdin=subprocess.PIPE if input_bytes is not None else None,  # nosec B603  # reason: argv list or CreateProcess line, never a shell
                               stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                               # its own process group on POSIX, so the timeout can end all of it
                               start_new_session=sys.platform != "win32")
    try:
        stdout, stderr = process.communicate(input_bytes, timeout=timeout_s)
    except subprocess.TimeoutExpired:
        _kill_tree(process)
        try:
            process.communicate(timeout=5)
        except subprocess.TimeoutExpired:
            autocontrol_logger.error("%s: output pipes still open after the kill", program_of(argv))
        raise
    return subprocess.CompletedProcess(argv, process.returncode, stdout, stderr)  # nosemgrep  # reason: runs nothing


class ShellManager:
    """
    ShellManager
    Shell 指令管理器
    - 執行外部 shell 指令 (不使用 shell=True，避免注入)
    - 使用背景執行緒持續讀取 stdout / stderr
    - 將輸出放入 queue，供 pull_text() 取出
    """

    def __init__(self, shell_encoding: Optional[str] = None, program_buffer: int = 10240000):
        """
        :param shell_encoding: shell command read output encoding; by default
            the locale's, which is what a console program writes on Windows
            (UTF-8 turned ``磁碟區`` into replacement characters)
        :param program_buffer: buffer size
        """
        self.read_program_error_output_from_thread: Union[Thread, None] = None
        self.read_program_output_from_thread: Union[Thread, None] = None
        self.still_run_shell: bool = False
        self.process: Union[subprocess.Popen, None] = None
        self.run_output_queue: queue.Queue = queue.Queue()
        self.run_error_queue: queue.Queue = queue.Queue()
        self.program_encoding: str = shell_encoding or console_encoding()
        self.program_buffer: int = program_buffer

    def exec_shell(self, shell_command: Union[str, List[str], None] = None, *,
                   command: Union[str, List[str], None] = None) -> None:
        """
        Execute shell command with shell=False.
        執行 shell 指令 (shell=False，呼叫端需自備 argv 或可被 shlex 切分的字串)

        ``command`` is accepted as another name for ``shell_command`` -- the
        name ``AC_shell_to_var`` and the documented examples use. The manager
        runs one program at a time: starting another ends the one before.
        A program that cannot start raises ``AutoControlActionException``;
        it used to be logged and reported as success.
        """
        shell_command = shell_command if shell_command is not None else command
        if shell_command is None:
            raise ValueError("exec_shell needs shell_command")
        autocontrol_logger.info("exec_shell: %s", program_of(shell_command))
        try:
            self.exit_program()
            args = command_args(shell_command)
            refuse_batch_metacharacters(args)
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
            raise AutoControlActionException(
                f"exec_shell: {program_of(shell_command)} could not start: {error}") from error

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
            self._terminate_and_reap(self.process)
            self.process = None

        self.log_and_clear_queue()

    def _terminate_and_reap(self, process: subprocess.Popen) -> None:
        """Terminate ``process``, wait for the real exit code, and reap it."""
        process.terminate()
        try:
            process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            process.kill()
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                autocontrol_logger.error("Shell command did not exit after kill")
        autocontrol_logger.info(
            f"Shell command exit with code {process.returncode}"
        )

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
