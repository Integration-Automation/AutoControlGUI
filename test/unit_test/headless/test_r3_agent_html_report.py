"""Round-3 regression: HTML report generation must escape recorded values so a
param/exception containing <, >, & cannot inject markup (stored XSS / malformed
report)."""
import html

from je_auto_control.utils.generate_report.generate_html_report import (
    make_html_table,
)


def _record(param):
    return {
        "function_name": "AC_write",
        "local_param": param,
        "time": "2026-07-17T00:00:00",
        "program_exception": "None",
    }


def test_html_metacharacters_in_param_are_escaped():
    payload = "<script>alert('xss')</script>"
    out = make_html_table("", _record(payload), "event_table_head")
    assert payload not in out
    assert html.escape(payload) in out
    assert "&lt;script&gt;" in out


def test_ampersand_and_angle_brackets_escaped():
    out = make_html_table("", _record("a & b < c"), "event_table_head")
    assert "a &amp; b &lt; c" in out
    assert "a & b < c" not in out


def test_exception_field_is_escaped():
    record = _record("ok")
    record["program_exception"] = "<b>boom</b>"
    out = make_html_table("", record, "failure_table_head")
    assert "<b>boom</b>" not in out
    assert "&lt;b&gt;boom&lt;/b&gt;" in out


def test_none_values_render_as_literal_none():
    record = {
        "function_name": None, "local_param": None,
        "time": None, "program_exception": None,
    }
    out = make_html_table("", record, "event_table_head")
    assert "None" in out
