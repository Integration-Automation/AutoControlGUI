"""CI-native report output for :class:`TestSuiteResult`.

* :func:`write_junit_xml` emits a JUnit XML file that Jenkins, GitHub
  Actions, GitLab CI, and most test dashboards parse natively.
* :func:`write_allure_results` emits one Allure-2 ``*-result.json`` file
  per case into a results directory, ready for ``allure generate``.

Only *generation* happens here (never parsing untrusted XML), so the
stdlib ``xml.etree.ElementTree`` writer is safe to use.
"""
from __future__ import annotations

import datetime
import json
import uuid
# Write-only XML generation; never parses untrusted input.
import xml.etree.ElementTree as ET  # nosemgrep  # nosec B405  # reason: see above
from pathlib import Path
from typing import Any, Dict, List, Tuple

from je_auto_control.utils.test_suite.result import (
    STATUS_ERROR, STATUS_FAILED, STATUS_SKIPPED, TestSuiteResult,
)
from je_auto_control.utils.xml.change_xml_structure.change_xml_structure import xml_safe_text

_ALLURE_STATUS = {
    "passed": "passed",
    STATUS_FAILED: "failed",
    STATUS_ERROR: "broken",
    STATUS_SKIPPED: "skipped",
}


def _case_element(parent: ET.Element, case: Any, suite_name: str) -> None:
    """Append one ``<testcase>`` (with failure/error/skipped child) element."""
    # Messages are str(error) / OCR text / captured output: an ANSI colour
    # code in one made the whole file unreadable to every CI system.
    message = xml_safe_text(case.message)
    node = ET.SubElement(parent, "testcase", {
        "name": xml_safe_text(case.name),
        "classname": suite_name,
        "time": f"{case.duration_s:.3f}",
    })
    if case.status == STATUS_FAILED:
        child = ET.SubElement(node, "failure", {"message": message})
        child.text = message
    elif case.status == STATUS_ERROR:
        child = ET.SubElement(node, "error", {"message": message})
        child.text = message
    elif case.status == STATUS_SKIPPED:
        ET.SubElement(node, "skipped", {"message": message})


def to_junit_xml(result: TestSuiteResult) -> str:
    """Render ``result`` as a JUnit XML string."""
    suites = ET.Element("testsuites")
    suite_name = xml_safe_text(result.name)
    # A setup failure is written as a ``<setup>`` testcase with an error, so
    # it is counted too: readers that trust the attributes saw an empty,
    # green suite (tests="0" errors="0").
    setup_failed = 1 if result.setup_error else 0
    suite = ET.SubElement(suites, "testsuite", {
        "name": suite_name,
        "tests": str(result.total + setup_failed),
        "failures": str(result.failed),
        "errors": str(result.errored + setup_failed),
        "skipped": str(result.skipped),
        "time": f"{result.duration_s:.3f}",
        "timestamp": datetime.datetime.fromtimestamp(
            result.started_at).isoformat(timespec="seconds"),
    })
    if result.setup_error:
        setup_error = xml_safe_text(result.setup_error)
        error_case = ET.SubElement(suite, "testcase", {
            "name": "<setup>", "classname": suite_name, "time": "0.000",
        })
        node = ET.SubElement(error_case, "error", {"message": setup_error})
        node.text = setup_error
    for case in result.cases:
        _case_element(suite, case, suite_name)
    return ET.tostring(suites, encoding="unicode")


def write_junit_xml(result: TestSuiteResult, path: str) -> str:
    """Write the JUnit XML for ``result`` to ``path``; return the path."""
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    xml = "<?xml version='1.0' encoding='utf-8'?>\n" + to_junit_xml(result)
    target.write_text(xml, encoding="utf-8")
    return str(target)


def _utf8(text: str) -> str:
    """``text`` with lone surrogates replaced, so it can be written as UTF-8.

    One ``\\ud800`` in a name or message raised ``UnicodeEncodeError``
    part-way through writing the result files.
    """
    return text.encode("utf-8", "replace").decode("utf-8")


def _allure_payload(result: TestSuiteResult, name: str, status: str,
                    message: str, tags: List[str],
                    span_ms: Tuple[int, int] = (0, 0)) -> Dict[str, Any]:
    labels = [{"name": "suite", "value": _utf8(result.name)}]
    labels.extend({"name": "tag", "value": _utf8(tag)} for tag in tags)
    payload: Dict[str, Any] = {
        "uuid": str(uuid.uuid4()),
        "name": _utf8(name),
        "fullName": _utf8(f"{result.name}#{name}"),
        "status": status,
        "labels": labels,
        # Allure reads a result's duration from start/stop (epoch ms); without
        # them every case showed no duration.
        "start": span_ms[0],
        "stop": span_ms[1],
    }
    if message:
        payload["statusDetails"] = {"message": _utf8(message)}
    return payload


def _allure_case(result: TestSuiteResult, case: Any,
                 start_s: float) -> Dict[str, Any]:
    """Build one Allure-2 result dict for a case that started at ``start_s`` (epoch)."""
    stop_s = start_s + max(float(case.duration_s or 0.0), 0.0)
    return _allure_payload(result, case.name,
                           _ALLURE_STATUS.get(case.status, "unknown"),
                           case.message, list(case.tags),
                           (round(start_s * 1000), round(stop_s * 1000)))


def _case_starts(result: TestSuiteResult) -> List[float]:
    """Each case's start (epoch seconds): the cases run one after another from ``started_at``."""
    starts, clock = [], float(result.started_at)
    for case in result.cases:
        starts.append(clock)
        clock += max(float(case.duration_s or 0.0), 0.0)
    return starts


def to_allure_results(result: TestSuiteResult) -> List[Dict[str, Any]]:
    """Return the list of Allure-2 result dicts for ``result``.

    A setup failure is a ``broken`` ``<setup>`` result, as in the JUnit
    report; it used to produce no result at all, so Allure showed nothing.
    """
    payloads = [_allure_case(result, case, start)
                for case, start in zip(result.cases, _case_starts(result))]
    if result.setup_error:
        started_ms = round(float(result.started_at) * 1000)
        payloads.insert(0, _allure_payload(result, "<setup>", "broken",
                                           result.setup_error, [],
                                           (started_ms, started_ms)))
    return payloads


def write_allure_results(result: TestSuiteResult, directory: str) -> List[str]:
    """Write one ``<uuid>-result.json`` per case into ``directory``."""
    target_dir = Path(directory)
    target_dir.mkdir(parents=True, exist_ok=True)
    written: List[str] = []
    for payload in to_allure_results(result):
        file_path = target_dir / f"{payload['uuid']}-result.json"
        file_path.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        written.append(str(file_path))
    return written
