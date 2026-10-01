"""OCR helpers for locating and interacting with on-screen text."""
from je_auto_control.utils.ocr.ocr_engine import (
    TextMatch, click_text, find_text_matches, locate_text_center,
    set_tesseract_cmd, wait_for_text,
)
from je_auto_control.utils.ocr.tesseract_setup import (
    OCRStatus, find_tesseract_cmd, ocr_languages, ocr_status, set_tessdata_dir,
)
from je_auto_control.utils.ocr.text_span import find_spans, group_lines

__all__ = [
    "OCRStatus", "TextMatch", "click_text", "find_spans", "find_tesseract_cmd",
    "find_text_matches", "group_lines", "locate_text_center", "ocr_languages",
    "ocr_status", "set_tessdata_dir", "set_tesseract_cmd", "wait_for_text",
]
