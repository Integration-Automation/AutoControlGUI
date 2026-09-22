"""Regression tests for the report-generation defects of the 2026-09-23 audit.

ElementTree writes characters XML 1.0 forbids as they are, so a recorded
``\\x01`` or an ANSI colour code made the XML report raise ``ExpatError`` (outside
the ``AutoControlException`` family, so it aborted the script) and the JUnit
file unreadable by CI. A report that could not be written was logged and
dropped, and exception text was quoted twice.
"""
import xml.dom.minidom

import pytest

from je_auto_control.utils.exception.exceptions import (
    AutoControlGenerateJsonReportException, AutoControlHTMLException, XMLException,
)
from je_auto_control.utils.generate_report.generate_html_report import generate_html_report
from je_auto_control.utils.generate_report.generate_json_report import generate_json_report
from je_auto_control.utils.generate_report.generate_xml_report import generate_xml_report
from je_auto_control.utils.test_record.record_test_class import (
    record_action_to_list, test_record_instance,
)
from je_auto_control.utils.test_suite.reports import to_junit_xml
from je_auto_control.utils.test_suite import result as suite_result


@pytest.fixture
def records():
    previous = test_record_instance.init_record
    test_record_instance.clean_record()
    test_record_instance.set_record_enable(True)
    yield
    test_record_instance.clean_record()
    test_record_instance.set_record_enable(previous)


def test_the_xml_report_survives_control_characters(records, tmp_path):
    record_action_to_list("step\x01", "p\x1b[31m", None)
    record_action_to_list("bad\x0b", None, repr(ValueError("x\x02")))
    generate_xml_report(str(tmp_path / "r"))
    for name in ("r_success.xml", "r_failure.xml"):
        xml.dom.minidom.parse(str(tmp_path / name))  # well-formed


def test_the_junit_report_survives_control_characters():
    result = suite_result.TestSuiteResult(name="suite\x01", cases=[
        suite_result.TestCaseResult(name="c\x1b", status="failed", message="got \x1b[31mred\x1b[0m"),
    ])
    parsed = xml.dom.minidom.parseString(to_junit_xml(result))
    failure = parsed.getElementsByTagName("failure")[0]
    assert "red" in failure.getAttribute("message")


@pytest.mark.parametrize("generate, error", [
    (generate_html_report, AutoControlHTMLException),
    (generate_json_report, AutoControlGenerateJsonReportException),
    (generate_xml_report, XMLException),
])
def test_a_report_that_cannot_be_written_raises(records, tmp_path, generate, error):
    record_action_to_list("step", None, None)
    with pytest.raises(error, match="cannot write report"):
        generate(str(tmp_path / "no_such_dir" / "report"))


def test_exception_text_is_not_quoted_twice(records):
    record_action_to_list("step", None, repr(ValueError("boom")))
    record_action_to_list("ok", None, None)
    exceptions = [row["program_exception"] for row in test_record_instance.test_record_list]
    assert exceptions == ["ValueError('boom')", "None"]
