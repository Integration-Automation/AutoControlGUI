"""Headless tests for the log handler's encoding policy.

These matter on a non-UTF-8 console locale (zh-TW Windows defaults to cp950).
The project's own log messages are bilingual CJK, and logging swallows handler
errors into a stderr notice — so an encoding mistake here does not raise, it
silently drops log records.
"""
import io
import logging
from contextlib import redirect_stderr

import pytest

from je_auto_control.utils.logging.logging_instance import (
    AutoControlGUILoggingHandler,
)

# U+2810 braille (seen live in device_matrix output) and an emoji: both are
# outside CP950 and outside most non-UTF-8 Windows code pages.
_NON_CP950 = "braille ⠐ and emoji \U0001F600 and CJK 中文"


@pytest.fixture()
def handler(tmp_path):
    made = AutoControlGUILoggingHandler(filename=str(tmp_path / "t.log"))
    yield made
    made.close()


def test_handler_stream_is_utf8_not_the_platform_default(handler):
    """Regression: encoding was left unset, so the stream took the platform
    default — cp950 on a zh-TW box — rather than utf-8."""
    assert handler.stream.encoding.lower().replace("-", "") == "utf8"


def test_non_cp950_characters_do_not_break_emit(handler, tmp_path):
    """A record containing non-CP950 characters must be written, not dropped.

    Regression: this raised UnicodeEncodeError inside emit(); logging caught
    it, printed '--- Logging error ---' to stderr, and lost the record.
    """
    log = logging.getLogger("test_logging_encoding_case")
    log.setLevel(logging.DEBUG)
    log.propagate = False
    log.addHandler(handler)
    try:
        captured = io.StringIO()
        with redirect_stderr(captured):
            log.info(_NON_CP950)
            handler.flush()
        assert "UnicodeEncodeError" not in captured.getvalue()
        assert "--- Logging error ---" not in captured.getvalue()
    finally:
        log.removeHandler(handler)

    written = (tmp_path / "t.log").read_text(encoding="utf-8")
    assert "⠐" in written
    assert "中文" in written


def test_encoding_is_overridable(tmp_path):
    """The default is utf-8, but callers may still choose."""
    made = AutoControlGUILoggingHandler(
        filename=str(tmp_path / "o.log"), encoding="utf-16",
    )
    try:
        assert made.stream.encoding.lower().replace("-", "") == "utf16"
    finally:
        made.close()


def test_a_lone_surrogate_degrades_instead_of_dropping_the_record(
        handler, tmp_path):
    """utf-8 alone is not enough to guarantee a record is never dropped.

    Windows paths read via surrogateescape can carry lone surrogates, and this
    library logs paths. Those still raise under a strict errors policy, so the
    handler pins backslashreplace — the same default logging.basicConfig uses.
    """
    log = logging.getLogger("test_logging_surrogate_case")
    log.setLevel(logging.DEBUG)
    log.propagate = False
    log.addHandler(handler)
    try:
        captured = io.StringIO()
        with redirect_stderr(captured):
            log.info("path with lone surrogate: \udcff")
            handler.flush()
        assert "UnicodeEncodeError" not in captured.getvalue()
    finally:
        log.removeHandler(handler)

    written = (tmp_path / "t.log").read_text(encoding="utf-8")
    assert "lone surrogate" in written      # the record survived, escaped
