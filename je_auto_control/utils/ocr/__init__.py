"""OCR helpers for locating and interacting with on-screen text."""
from je_auto_control.utils.ocr.ocr_engine import (
    TextMatch, click_text, find_text_matches, locate_text_center,
    set_tesseract_cmd, wait_for_text,
)

__all__ = [
    "TextMatch", "click_text", "find_text_matches", "locate_text_center",
    "set_tesseract_cmd", "wait_for_text",
]
