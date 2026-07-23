import logging
from logging.handlers import RotatingFileHandler

# 設定 root logger 等級 Set root logger level
logging.root.setLevel(logging.DEBUG)

# 建立 AutoControlGUI 專用 logger Create dedicated logger
autocontrol_logger = logging.getLogger("AutoControlGUI")

# 日誌格式 Formatter
formatter = logging.Formatter(
    "%(asctime)s | %(name)s | %(levelname)s | %(message)s"
)


class AutoControlGUILoggingHandler(RotatingFileHandler):
    """
    AutoControlGUILoggingHandler
    自訂日誌處理器，繼承 RotatingFileHandler
    - 支援檔案大小輪替
    - 預設輸出到 AutoControlGUI.log
    """

    def __init__(
        self,
        filename: str = "AutoControlGUI.log",
        mode: str = "w",
        max_bytes: int = 1073741824,  # 1GB
        backup_count: int = 0,
        encoding: str = "utf-8",
        errors: str = "backslashreplace",
    ):
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
            filename=filename,
            mode=mode,
            maxBytes=max_bytes,
            backupCount=backup_count,
            encoding=encoding,
            errors=errors,
        )
        self.setFormatter(formatter)  # 設定格式器
        self.setLevel(logging.DEBUG)  # 設定等級

    def emit(self, record: logging.LogRecord) -> None:
        """
        Emit log record.
        輸出日誌紀錄
        """
        super().emit(record)


# 建立並加入檔案處理器 Add file handler to logger
file_handler = AutoControlGUILoggingHandler()
autocontrol_logger.addHandler(file_handler)