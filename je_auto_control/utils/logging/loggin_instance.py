import logging
import sys

auto_control_logger = logging.getLogger("AutoControl")
auto_control_logger.setLevel(logging.INFO)
formatter = logging.Formatter('%(asctime)s | %(name)s | %(levelname)s | %(message)s')
# Stream handler
stream_handler = logging.StreamHandler(stream=sys.stderr)
stream_handler.setFormatter(formatter)
stream_handler.setLevel(logging.WARNING)
auto_control_logger.addHandler(stream_handler)
# File handler
file_handler = logging.FileHandler("AutoControl.log")
file_handler.setFormatter(formatter)
auto_control_logger.addHandler(file_handler)
