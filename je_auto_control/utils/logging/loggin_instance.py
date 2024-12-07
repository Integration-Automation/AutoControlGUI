import logging

logging.root.setLevel(logging.DEBUG)
autocontrol_logger = logging.getLogger("AutoControlGUI")
formatter = logging.Formatter('%(asctime)s | %(name)s | %(levelname)s | %(message)s')
# File handler
file_handler = logging.FileHandler(filename="AutoControlGUI.log", mode="w")
file_handler.setFormatter(formatter)
autocontrol_logger.addHandler(file_handler)

class AutoControlLoggingHandler(logging.Handler):

    # redirect logging stderr output to queue

    def __init__(self):
        super().__init__()
        self.formatter = formatter
        self.setLevel(logging.DEBUG)

    def emit(self, record: logging.LogRecord) -> None:
        print(self.format(record))


# Stream handler
autocontrol_logger.addHandler(AutoControlLoggingHandler())
