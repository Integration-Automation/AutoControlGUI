import logging
from logging.handlers import RotatingFileHandler

logging.root.setLevel(logging.DEBUG)
autocontrol_logger = logging.getLogger("AutoControlGUI")
formatter = logging.Formatter('%(asctime)s | %(name)s | %(levelname)s | %(message)s')


class AutoControlGUILoggingHandler(RotatingFileHandler):

    # redirect logging stderr output to queue

    def __init__(self, filename: str = "AutoControlGUI.log", mode="w",
                 maxBytes: int = 1073741824, backupCount: int = 0):
        super().__init__(filename=filename, mode=mode, maxBytes=maxBytes, backupCount=backupCount)
        self.formatter = formatter
        self.setLevel(logging.DEBUG)

    def emit(self, record: logging.LogRecord) -> None:
        super().emit(record)


# File handler
file_handler = AutoControlGUILoggingHandler()
autocontrol_logger.addHandler(file_handler)
