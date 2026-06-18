"""Read text from PDF documents and assert on their content.

Backed by the optional ``pypdf`` package (pure-Python, MIT). The single
``_open_pdf`` seam imports it lazily and raises a clear ``RuntimeError``
when it is missing, mirroring the optional Excel backend in the
data-source loader; the rest of the module stays import-light. Imports no
``PySide6`` so PDF checks run fully headlessly.
"""
import os
from typing import Any, Dict, Iterable, List, Optional, Union

from je_auto_control.utils.exception.exceptions import AutoControlAssertionException

PageSelector = Optional[Union[int, Iterable[int]]]


def _open_pdf(path: str):
    """Return a ``pypdf.PdfReader`` for an existing PDF; raise if unavailable."""
    try:
        from pypdf import PdfReader
    except ImportError as error:
        raise RuntimeError(
            "PDF features require pypdf (pip install pypdf).") from error
    real = os.path.realpath(path)
    if not os.path.isfile(real):
        raise FileNotFoundError(f"PDF not found: {path}")
    return PdfReader(real)


def _page_indices(pages: PageSelector, total: int) -> List[int]:
    """Translate a 1-based page selector into 0-based indices (or all pages)."""
    if pages is None:
        return list(range(total))
    wanted = [pages] if isinstance(pages, int) else [int(p) for p in pages]
    indices: List[int] = []
    for one_based in wanted:
        index = int(one_based) - 1
        if not 0 <= index < total:
            raise ValueError(f"page {one_based} out of range 1..{total}")
        indices.append(index)
    return indices


def extract_pdf_text(path: str, pages: PageSelector = None) -> str:
    """Extract text from a PDF; ``pages`` is None (all), a 1-based page, or list."""
    reader = _open_pdf(path)
    indices = _page_indices(pages, len(reader.pages))
    return "\n".join(reader.pages[i].extract_text() or "" for i in indices)


def pdf_page_count(path: str) -> int:
    """Return the number of pages in a PDF."""
    return len(_open_pdf(path).pages)


def pdf_metadata(path: str) -> Dict[str, Any]:
    """Return the PDF's document metadata (keys without the leading slash)."""
    meta = _open_pdf(path).metadata or {}
    return {str(key).lstrip("/"): str(value) for key, value in dict(meta).items()}


def assert_pdf_text(path: str, text: str, *, present: bool = True,
                    page: PageSelector = None, case_sensitive: bool = True,
                    raise_on_fail: bool = True) -> Dict[str, Any]:
    """Assert ``text`` is present (or absent) in a PDF, optionally on ``page``."""
    extracted = extract_pdf_text(path, pages=page)
    haystack = extracted if case_sensitive else extracted.lower()
    needle = str(text) if case_sensitive else str(text).lower()
    found = needle in haystack
    passed = (found == bool(present))
    where = f" on page {page}" if page is not None else ""
    state = "contains" if found else "does not contain"
    message = f"assert_pdf_text: PDF{where} {state} {text!r} (present={present})"
    if not passed and raise_on_fail:
        raise AutoControlAssertionException(message)
    return {"kind": "pdf_text", "passed": passed, "message": message}
