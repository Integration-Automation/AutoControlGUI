"""QA suite orchestration — score action lists as test cases.

Public surface::

    from je_auto_control import (
        run_suite, TestCaseResult, TestSuiteResult,
    )
"""
from je_auto_control.utils.test_suite.result import (
    STATUS_ERROR, STATUS_FAILED, STATUS_PASSED, STATUS_SKIPPED,
    TestCaseResult, TestSuiteResult,
)
from je_auto_control.utils.test_suite.reports import (
    to_allure_results, to_junit_xml, write_allure_results, write_junit_xml,
)
from je_auto_control.utils.test_suite.runner import run_suite


__all__ = [
    "STATUS_ERROR", "STATUS_FAILED", "STATUS_PASSED", "STATUS_SKIPPED",
    "TestCaseResult", "TestSuiteResult", "run_suite",
    "to_allure_results", "to_junit_xml",
    "write_allure_results", "write_junit_xml",
]
