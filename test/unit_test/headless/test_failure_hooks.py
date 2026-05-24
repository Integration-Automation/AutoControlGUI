"""Tests for the failure-hook → ticket fan-out."""
from unittest.mock import patch

import pytest

from je_auto_control.utils.failure_hooks import (
    FailureHookManager, FailureReport, GitHubBackend, JiraBackend,
    LinearBackend, TicketResult,
)
from je_auto_control.utils.failure_hooks.backends import _post_json


# === FailureReport rendering ==============================================

def test_failure_report_renders_summary_and_body():
    report = FailureReport(
        source="scheduler", source_id="nightly",
        error_text="boom\ntraceback", script_path="x.json",
        screenshot_path="screenshot.png", log_tail="last line",
        metadata={"region": "us-east"},
    )
    summary = report.render_summary()
    body = report.render_body()
    assert "scheduler" in summary
    assert "nightly" in summary
    assert "boom" in summary  # first line of error
    assert "boom" in body
    assert "x.json" in body
    assert "us-east" in body


def test_failure_report_summary_handles_blank_error():
    report = FailureReport(source="s", source_id="id", error_text="")
    assert "failure" in report.render_summary()


# === Manager =============================================================

class _FakeBackend:
    name = "fake"

    def __init__(self, result: TicketResult) -> None:
        self._result = result
        self.calls = 0

    def create_issue(self, _report: FailureReport) -> TicketResult:
        self.calls += 1
        return self._result


class _AnotherFake(_FakeBackend):
    name = "another"


@pytest.fixture
def manager() -> FailureHookManager:
    return FailureHookManager()


def test_manager_register_validates_protocol(manager):
    with pytest.raises(TypeError):
        manager.register(object())


def test_manager_fire_dispatches_to_every_backend(manager):
    a = _FakeBackend(TicketResult(backend="fake", succeeded=True,
                                    ticket_id="A-1"))
    b = _AnotherFake(TicketResult(backend="another", succeeded=True,
                                    ticket_id="A-2"))
    manager.register(a)
    manager.register(b)
    results = manager.fire(FailureReport(source="s", source_id="id"))
    assert len(results) == 2
    assert a.calls == 1 and b.calls == 1


def test_manager_swallows_backend_exceptions(manager):
    class _Boom:
        name = "boom"

        def create_issue(self, _report):
            raise RuntimeError("nope")

    manager.register(_Boom())
    results = manager.fire(FailureReport(source="s", source_id="id"))
    assert len(results) == 1
    assert results[0].succeeded is False
    assert "nope" in results[0].error


def test_manager_can_be_disabled(manager):
    backend = _FakeBackend(TicketResult(backend="fake", succeeded=True,
                                          ticket_id="T-1"))
    manager.register(backend)
    manager.enable(False)
    assert manager.fire(FailureReport(source="s", source_id="id")) == []
    assert backend.calls == 0


def test_manager_unregister_drops_named_backend(manager):
    manager.register(_FakeBackend(TicketResult(backend="fake",
                                                 succeeded=True)))
    assert manager.unregister("fake") is True
    assert manager.list_backends() == []


def test_manager_list_backends_reports_name_and_type(manager):
    manager.register(_FakeBackend(TicketResult(backend="fake",
                                                 succeeded=True)))
    rows = manager.list_backends()
    assert rows == [{"name": "fake", "type": "_FakeBackend"}]


# === Concrete backends (HTTP mocked) =====================================

def test_github_backend_posts_to_repo_issues_endpoint():
    backend = GitHubBackend(owner="acme", repo="ops", token="t")
    captured = {}

    def fake_post(name, url, body, *, headers, **_kw):
        captured["url"] = url
        captured["body"] = body
        captured["headers"] = headers
        return TicketResult(backend=name, succeeded=True,
                              ticket_id="123",
                              url="https://github.com/acme/ops/issues/123")

    with patch(
        "je_auto_control.utils.failure_hooks.backends._post_json",
        side_effect=fake_post,
    ):
        result = backend.create_issue(FailureReport(
            source="s", source_id="id", error_text="boom",
        ))
    assert "/repos/acme/ops/issues" in captured["url"]
    assert captured["headers"]["Authorization"] == "token t"
    assert result.ticket_id == "123"


def test_jira_backend_basic_auth_header():
    backend = JiraBackend(
        base_url="https://acme.atlassian.net", email="a@b.com",
        api_token="t", project_key="OPS",
    )
    captured = {}

    def fake_post(name, url, body, *, headers, **_kw):
        captured["url"] = url
        captured["headers"] = headers
        return TicketResult(backend=name, succeeded=True,
                              ticket_id="OPS-1",
                              url="https://acme.atlassian.net/browse/OPS-1")

    with patch(
        "je_auto_control.utils.failure_hooks.backends._post_json",
        side_effect=fake_post,
    ):
        result = backend.create_issue(FailureReport(
            source="s", source_id="id",
        ))
    assert "/rest/api/3/issue" in captured["url"]
    assert captured["headers"]["Authorization"].startswith("Basic ")
    assert result.ticket_id == "OPS-1"


def test_linear_backend_posts_graphql_mutation():
    backend = LinearBackend(api_key="key", team_id="t-id")
    captured = {}

    def fake_post(name, url, body, *, headers, response_extractor, **_kw):
        captured["url"] = url
        captured["body"] = body
        return response_extractor(name, {
            "data": {"issueCreate": {
                "success": True,
                "issue": {"identifier": "ENG-7",
                           "url": "https://linear.app/x/issue/ENG-7"},
            }},
        })

    with patch(
        "je_auto_control.utils.failure_hooks.backends._post_json",
        side_effect=fake_post,
    ):
        result = backend.create_issue(FailureReport(
            source="s", source_id="id",
        ))
    assert "/graphql" in captured["url"]
    assert "issueCreate" in captured["body"]["query"]
    assert result.ticket_id == "ENG-7"


# === _post_json hardening ===============================================

def test_post_json_refuses_non_http_url():
    # NOSONAR python:S5332 — the literal is a *negative* test input,
    # not a URL we ever connect to; the backend rejects it.
    result = _post_json("test", "ftp://bad", {}, headers={})
    assert result.succeeded is False
    assert "non-HTTP" in result.error


def test_post_json_handles_url_error():
    import urllib.error
    with patch(
        "urllib.request.urlopen",
        side_effect=urllib.error.URLError("disconnected"),
    ):
        result = _post_json("test", "https://example.com",
                              {}, headers={}, id_key="id")
    assert result.succeeded is False
    assert "disconnected" in result.error


# === Executor / MCP / facade =============================================

def test_executor_registers_failure_hook_commands():
    from je_auto_control.utils.executor.action_executor import executor
    assert {
        "AC_failure_hook_fire", "AC_failure_hook_list",
        "AC_failure_hook_clear",
    } <= executor.known_commands()


def test_mcp_factory_registers_failure_hook_tools():
    from je_auto_control.utils.mcp_server.tools import (
        build_default_tool_registry,
    )
    names = {tool.name for tool in build_default_tool_registry()}
    assert {"ac_failure_hook_fire", "ac_failure_hook_list"} <= names


def test_facade_exports_failure_hook_api():
    import je_auto_control as ac
    for name in ("FailureReport", "FailureHookManager",
                  "GitHubBackend", "JiraBackend", "LinearBackend",
                  "TicketResult", "default_failure_hook_manager"):
        assert hasattr(ac, name)
