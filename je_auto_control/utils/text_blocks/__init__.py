"""Group OCR lines into paragraphs and bulleted / numbered lists."""
from je_auto_control.utils.text_blocks.text_blocks import (
    detect_lists, group_paragraphs,
)

__all__ = ["group_paragraphs", "detect_lists"]
