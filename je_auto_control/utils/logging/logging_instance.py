"""The ``AutoControlGUI`` logger and the file it writes to.

The log file lives at ``~/.je_auto_control/logs/AutoControlGUI.log`` unless the
``JE_AUTOCONTROL_LOG_FILE`` environment variable names another path (a relative
one resolves against the cwd at import time; ``os.devnull`` turns the file off).
It used to be the relative path ``AutoControlGUI.log``, opened at import, so
every process that imported the package -- including every pytest run on a
machine where it is installed, through its ``pytest11`` plugin -- left a log in
whatever directory it happened to start in.

The package's handler opens the file on the first record, not at import:
importing writes nothing (``test_facade_import_is_light`` holds that for the
whole state directory). The file is shared by every process on the account, so
it is opened for append, each line carries the process id, and it is rotated
only when a process opens it: renaming a file another process holds open fails
on Windows, and a rotation attempted inside ``emit()`` would then fail on every
later record.
"""
import logging
import os
import warnings
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import Optional

# 設定 root logger 等級 Set root logger level
logging.root.setLevel(logging.DEBUG)

# 建立 AutoControlGUI 專用 logger Create dedicated logger
autocontrol_logger = logging.getLogger("AutoControlGUI")

# 日誌格式 Formatter
formatter = logging.Formatter(
    "%(asctime)s | %(process)d | %(name)s | %(levelname)s | %(message)s"
)

#: Environment variable that overrides where the log file is written.
LOG_FILE_ENV = "JE_AUTOCONTROL_LOG_FILE"

#: A file past this size is moved to ``<name>.1`` when a process opens it.
ROTATE_AT_BYTES = 10 * 1024 * 1024


def default_log_file() -> Path:
    """Return the log file path: ``$JE_AUTOCONTROL_LOG_FILE``, else the home default."""
    configured = os.environ.get(LOG_FILE_ENV, "").strip()
    if configured:
        return Path(configured).expanduser()
    return Path.home() / ".je_auto_control" / "logs" / "AutoControlGUI.log"


def _rotate_if_large(path: Path, limit: int) -> None:
    """Move ``path`` to ``<path>.1`` when it is larger than ``limit`` bytes.

    Best effort: while another process has the file open Windows refuses the
    rename, and the file is simply appended to until a later open succeeds.
    """
    try:
        if limit <= 0 or not path.is_file() or path.stat().st_size <= limit:
            return
        os.replace(path, path.with_name(path.name + ".1"))
    except OSError:
        return


class AutoControlGUILoggingHandler(RotatingFileHandler):
    """
    AutoControlGUILoggingHandler
    自訂日誌處理器，繼承 RotatingFileHandler
    - 預設輸出到 ``default_log_file()``，附加模式
    - 開檔時建立目錄；超過 ``ROTATE_AT_BYTES`` 就先輪替成 ``.1``
    - 開不了檔就改寫到 ``os.devnull``，並發出一次 ``RuntimeWarning``

    ``delay=True`` defers opening (and so creating the directory) to the first
    record, which is how the package's own handler is built.
    """

    def __init__(
        self,
        filename: Optional[str] = None,
        mode: str = "a",
        max_bytes: int = 0,
        backup_count: int = 0,
        encoding: str = "utf-8",
        errors: str = "backslashreplace",
        delay: bool = False,
    ):
        path = filename if filename is not None else str(default_log_file())
        # encoding 必須明確指定。省略時 RotatingFileHandler 會採用系統
        # 預設編碼（zh-TW Windows 為 cp950），任何非 CP950 字元都會讓
        # emit() 拋出 UnicodeEncodeError；logging 會把它吞成 stderr 訊息，
        # 該筆日誌就此靜默遺失。本專案的訊息本身即為中英雙語。
        # encoding must be explicit. Without it RotatingFileHandler falls back
        # to the platform default (cp950 on zh-TW Windows), so any character
        # outside CP950 makes emit() raise UnicodeEncodeError — which logging
        # swallows into a stderr notice, silently dropping the record. This
        # project's own log messages are bilingual CJK.
        #
        # errors 同樣不能留白：utf-8 雖能編碼所有合法字元，但落單的
        # surrogate（Windows 路徑經 surrogateescape 讀入時會帶）在 strict
        # 下仍會拋錯。logging.basicConfig 自身的預設就是 backslashreplace。
        # errors matters too: utf-8 covers all valid text, but a lone surrogate
        # (Windows paths carry them via surrogateescape, and this library logs
        # paths) still raises under strict. backslashreplace is what
        # logging.basicConfig itself defaults to — degrade, never drop.
        super().__init__(
            filename=path,
            mode=mode,
            maxBytes=max_bytes,
            backupCount=backup_count,
            encoding=encoding,
            delay=delay,
            errors=errors,
        )
        self.setFormatter(formatter)  # 設定格式器
        self.setLevel(logging.DEBUG)  # 設定等級

    def _open(self):
        """Open the file, creating its directory and rotating it first.

        A file that cannot be opened (read-only home, a path through a regular
        file) must not turn every later record into a logging error, nor make
        the import fail: the handler writes to ``os.devnull`` instead and says
        so once.
        """
        path = Path(self.baseFilename)
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            _rotate_if_large(path, ROTATE_AT_BYTES)
            return super()._open()
        except OSError as error:
            warnings.warn(
                f"AutoControlGUI log file {path} unavailable, file logging "
                f"off: {error!r}", RuntimeWarning, stacklevel=2)
            return open(os.devnull, self.mode, encoding=self.encoding,  # noqa: SIM115  # reason: the handler owns and closes its stream
                        errors=self.errors)

    def emit(self, record: logging.LogRecord) -> None:
        """
        Emit log record.
        輸出日誌紀錄
        """
        super().emit(record)


# 建立並加入檔案處理器 Add file handler to logger
file_handler = AutoControlGUILoggingHandler(delay=True)
autocontrol_logger.addHandler(file_handler)
