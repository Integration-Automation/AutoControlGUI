"""CI-native report output for :class:`TestSuiteResult`.

* :func:`write_junit_xml` emits a JUnit XML file that Jenkins, GitHub
  Actions, GitLab CI, and most test dashboards parse natively.
* :func:`write_allure_results` emits one Allure-2 ``*-result.json`` file
  per case into a results directory, ready for ``allure generate``.

Only *generation* happens here (never parsing untrusted XML), so the
stdlib ``xml.etree.ElementTree`` writer is safe to use.
"""
from __future__ import annotations

import json
import uuid
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Any, Dict, List

from je_auto_control.utils.test_suite.result import (
    STATUS_ERROR, STATUS_FAILED, STATUS_SKIPPED, TestSuiteResult,
)

_ALLURE_STATUS = {
    "passed": "passed",
    STATUS_FAILED: "failed",
    STATUS_ERROR: "broken",
    STATUS_SKIPPED: "skipped",
}


def _case_element(parent: ET.Element, case: Any, suite_name: str) -> None:
    """Append one ``<testcase>`` (with failure/error/skipped child) element."""
    node = ET.SubElement(parent, "testcase", {
        "name": case.name,
        "classname": suite_name,
        "time": f"{case.duration_s:.3f}",
    })
    if case.status == STATUS_FAILED:
        child = ET.SubElement(node, "failure", {"message": case.message})
        child.text = case.message
    elif case.status == STATUS_ERROR:
        child = ET.SubElement(node, "error", {"message": case.message})
        child.text = case.message
    elif case.status == STATUS_SKIPPED:
        ET.SubElement(node, "skipped", {"message": case.message})


def to_junit_xml(result: TestSuiteResult) -> str:
    """Render ``result`` as a JUnit XML string."""
    suites = ET.Element("testsuites")
    suite = ET.SubElement(suites, "testsuite", {
        "name": result.name,
        "tests": str(result.total),
        "failures": str(result.failed),
        "errors": str(result.errored),
        "skipped": str(result.skipped),
        "time": f"{result.duration_s:.3f}",
    })
    if result.setup_error:
        error_case = ET.SubElement(suite, "testcase", {
            "name": "<setup>", "classname": result.name, "time": "0.000",
        })
        node = ET.SubElement(error_case, "error",
                             {"message": result.setup_error})
        node.text = result.setup_error
    for case in result.cases:
        _case_element(suite, case, result.name)
    return ET.tostring(suites, encoding="unicode")


def write_junit_xml(result: TestSuiteResult, path: str) -> str:
    """Write the JUnit XML for ``result`` to ``path``; return the path."""
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    xml = "<?xml version='1.0' encoding='utf-8'?>\n" + to_junit_xml(result)
    target.write_text(xml, encoding="utf-8")
    return str(target)


def _allure_case(result: TestSuiteResult, case: Any) -> Dict[str, Any]:
    """Build one Allure-2 result dict for a case."""
    labels = [{"name": "suite", "value": result.name}]
    labels.extend({"name": "tag", "value": tag} for tag in case.tags)
    payload: Dict[str, Any] = {
        "uuid": str(uuid.uuid4()),
        "name": case.name,
        "fullName": f"{result.name}#{case.name}",
        "status": _ALLURE_STATUS.get(case.status, "unknown"),
        "labels": labels,
    }
    if case.message:
        payload["statusDetails"] = {"message": case.message}
    return payload


def to_allure_results(result: TestSuiteResult) -> List[Dict[str, Any]]:
    """Return the list of Allure-2 result dicts for ``result``."""
    return [_allure_case(result, case) for case in result.cases]


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
