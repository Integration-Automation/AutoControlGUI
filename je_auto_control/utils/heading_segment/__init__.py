"""Classify OCR lines as headings vs body and build a document outline."""
from je_auto_control.utils.heading_segment.heading_segment import (
    classify_lines, outline,
)

__all__ = ["classify_lines", "outline"]
