"""Phase 9.2: tests for the action JSON linter + schema generator."""
import json
from pathlib import Path

import pytest

from je_auto_control.utils.action_lint import (
    LintSeverity, build_action_schema, lint_actions, render_schema_json,
)
from je_auto_control.utils.action_lint.linter import ActionLinter, _main


# --- JSON Schema generator ------------------------------------------

def test_build_schema_lists_known_commands():
    schema = build_action_schema()
    assert schema["$schema"].startswith("https://json-schema.org/")
    assert schema["type"] == "array"
    items = schema["items"]["oneOf"]
    consts = {item["prefixItems"][0]["const"] for item in items}
    assert "AC_click_mouse" in consts
    assert "AC_screenshot" in consts


def test_render_schema_json_is_valid_json():
    raw = render_schema_json()
    parsed = json.loads(raw)
    assert parsed["type"] == "array"


def test_schema_include_only_filter():
    schema = build_action_schema(include_only=["AC_screenshot"])
    items = schema["items"]["oneOf"]
    assert len(items) == 1
    assert items[0]["prefixItems"][0]["const"] == "AC_screenshot"


# --- linter ---------------------------------------------------------

def _stub_linter():
    """A linter populated with a known synthetic command set."""

    def click(x: int, y: int, button: str = "left") -> None:
        return None

    def take_screenshot(file_path: str = "") -> None:
        return None

    return ActionLinter(known_commands={
        "AC_click": click,
        "AC_screenshot": take_screenshot,
    })


def test_lint_empty_list_is_clean():
    assert lint_actions([]) == []


def test_lint_non_list_root_raises():
    issues = lint_actions("not a list")  # type: ignore[arg-type]  # NOSONAR python:S5655  # reason: intentional bad-type negative test
    assert any(i.code == "not-a-list" for i in issues)


def test_lint_unknown_command_flagged():
    issues = _stub_linter().lint_actions([
        ["AC_does_not_exist", {}],
    ])
    codes = {i.code for i in issues}
    assert "unknown-command" in codes


def test_lint_missing_required_param_flagged():
    issues = _stub_linter().lint_actions([
        ["AC_click", {"x": 10}],  # missing y
    ])
    missing_codes = [i for i in issues if i.code == "missing-param"]
    assert len(missing_codes) == 1
    assert "'y'" in missing_codes[0].message
    assert missing_codes[0].severity == LintSeverity.ERROR


def test_lint_unknown_param_is_warning_not_error():
    issues = _stub_linter().lint_actions([
        ["AC_click", {"x": 1, "y": 2, "speed": "fast"}],
    ])
    unknown = [i for i in issues if i.code == "unknown-param"]
    assert len(unknown) == 1
    assert unknown[0].severity == LintSeverity.WARNING


def test_lint_skips_unknown_param_check_when_kwargs_present():
    """Commands declaring **kwargs accept anything — don't false-warn."""

    def kwargs_command(**kwargs):
        return None

    linter = ActionLinter(known_commands={"AC_kw": kwargs_command})
    issues = linter.lint_actions([
        ["AC_kw", {"anything": 1, "goes": 2}],
    ])
    assert all(i.code != "unknown-param" for i in issues)


def test_lint_bad_shape_rejected():
    linter = _stub_linter()
    issues = linter.lint_actions([
        "not-a-list",
        [],
        [42],
        ["AC_click", "not-a-dict"],
    ])
    codes = [i.code for i in issues]
    assert "bad-shape" in codes
    assert "empty-action" in codes
    assert "bad-name" in codes
    assert "bad-params" in codes


def test_lint_accepts_command_with_default_params():
    """A command that only has defaults should pass with no params at all."""
    issues = _stub_linter().lint_actions([
        ["AC_screenshot", {}],
        ["AC_screenshot"],
    ])
    assert issues == []


def test_lint_to_dict_round_trip():
    [issue] = lint_actions("not a list")  # type: ignore[arg-type]  # NOSONAR python:S5655  # reason: intentional bad-type negative test
    body = issue.to_dict()
    assert body["code"] == "not-a-list"
    assert body["severity"] == LintSeverity.ERROR


# --- CLI entry point ------------------------------------------------

def test_cli_exit_code_zero_on_clean_file(tmp_path):
    actions_file = tmp_path / "ok.action.json"
    actions_file.write_text(
        json.dumps([["AC_screenshot", {"file_path": "/tmp/x.png"}]]),
        encoding="utf-8",
    )
    assert _main([str(actions_file)]) == 0


def test_cli_exit_code_one_on_error(tmp_path, capsys):
    actions_file = tmp_path / "bad.action.json"
    actions_file.write_text(
        json.dumps([["AC_definitely_not_a_command", {}]]),
        encoding="utf-8",
    )
    rc = _main([str(actions_file)])
    assert rc == 1
    out = capsys.readouterr().out
    assert "unknown-command" in out


def test_cli_exit_code_one_on_missing_file(tmp_path, capsys):
    rc = _main([str(tmp_path / "missing.json")])
    assert rc == 1


def test_cli_no_args_returns_usage(capsys):
    rc = _main([])
    assert rc == 2
    err = capsys.readouterr().err
    assert "usage:" in err


# --- reusable GitHub Actions workflow file ---------------------------

def test_github_workflow_exists_and_calls_module():
    workflow = (
        Path(__file__).resolve().parents[3]
        / ".github" / "workflows" / "action-json-lint.yml"
    )
    raw = workflow.read_text(encoding="utf-8")
    assert "workflow_call:" in raw
    assert "je_auto_control.utils.action_lint" in raw
