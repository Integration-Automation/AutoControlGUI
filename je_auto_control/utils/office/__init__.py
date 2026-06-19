"""Headless read/write for Office documents (Excel / Word / PowerPoint)."""
from je_auto_control.utils.office.office import (
    read_document, read_presentation, read_workbook,
    write_document, write_presentation, write_workbook,
)

__all__ = [
    "read_workbook", "write_workbook",
    "read_document", "write_document",
    "read_presentation", "write_presentation",
]
