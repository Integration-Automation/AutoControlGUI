"""Read and assert on PDF documents (optional pypdf backend)."""
from je_auto_control.utils.pdf.pdf_reader import (
    assert_pdf_text,
    extract_pdf_text,
    pdf_metadata,
    pdf_page_count,
)

__all__ = [
    "assert_pdf_text", "extract_pdf_text", "pdf_metadata", "pdf_page_count",
]
