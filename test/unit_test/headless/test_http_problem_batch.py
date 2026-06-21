"""Headless tests for RFC 9457 problem+json parsing. Pure stdlib, no Qt."""
import json

import pytest

import je_auto_control as ac
from je_auto_control.utils.http_problem import (
    HttpProblemError, ProblemDetails, is_problem, parse_problem,
    raise_for_problem,
)

_PROBLEM = {
    "status": 403,
    "headers": {"Content-Type": "application/problem+json; charset=utf-8"},
    "json": {
        "type": "https://example.com/probs/forbidden",
        "title": "Forbidden",
        "status": 403,
        "detail": "Account is suspended",
        "instance": "/orders/12",
        "balance": 30,           # vendor extension
    },
}
_PLAIN = {"status": 200, "headers": {"Content-Type": "application/json"},
          "json": {"ok": True}}


def test_is_problem_detects_media_type():
    assert is_problem(_PROBLEM["headers"]) is True
    assert is_problem(_PLAIN["headers"]) is False
    assert is_problem({"content-type": "application/problem+json"}) is True
    assert is_problem(None) is False


def test_parse_registered_members_and_extensions():
    problem = parse_problem(_PROBLEM)
    assert isinstance(problem, ProblemDetails)
    assert problem.type.endswith("/forbidden")
    assert problem.title == "Forbidden" and problem.status == 403
    assert problem.detail == "Account is suspended"
    assert problem.extensions == {"balance": 30}
    assert "balance" in problem.to_dict()


def test_non_problem_returns_none():
    assert parse_problem(_PLAIN) is None


def test_parse_from_text_when_json_absent():
    response = {"status": 400,
                "headers": {"Content-Type": "application/problem+json"},
                "text": json.dumps({"title": "Bad", "status": 400})}
    problem = parse_problem(response)
    assert problem.title == "Bad" and problem.status == 400


def test_defaults_and_bad_status_coercion():
    response = {"headers": {"content-type": "application/problem+json"},
                "json": {"status": "not-a-number"}}
    problem = parse_problem(response)
    assert problem.type == "about:blank" and problem.status is None


def test_raise_for_problem():
    with pytest.raises(HttpProblemError) as info:
        raise_for_problem(_PROBLEM)
    assert info.value.problem.status == 403
    raise_for_problem(_PLAIN)          # no raise for a non-problem


# --- wiring ---------------------------------------------------------------

def test_executor_round_trip():
    rec = ac.execute_action([[
        "AC_parse_problem", {"response": json.dumps(_PROBLEM)}]])
    problem = next(v for v in rec.values() if isinstance(v, dict))["problem"]
    assert problem["title"] == "Forbidden" and problem["balance"] == 30
    rec2 = ac.execute_action([[
        "AC_parse_problem", {"response": json.dumps(_PLAIN)}]])
    assert next(v for v in rec2.values()
                if isinstance(v, dict))["problem"] is None


def test_wiring():
    assert "AC_parse_problem" in ac.executor.known_commands()
    from je_auto_control.utils.mcp_server.tools import build_default_tool_registry
    assert "ac_parse_problem" in {t.name for t in build_default_tool_registry()}
    from je_auto_control.gui.script_builder.command_schema import _build_specs
    assert "AC_parse_problem" in {s.command for s in _build_specs()}


def test_facade_exports():
    for attr in ("HttpProblemError", "ProblemDetails", "is_problem",
                 "parse_problem", "raise_for_problem"):
        assert hasattr(ac, attr) and attr in ac.__all__
