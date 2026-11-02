"""Compile rooted CSV forms and captured field transfers into reviewed WebRunner task actions."""
# pylint: disable=import-outside-toplevel  # reason: reuse shared compiler helpers without an import cycle
from __future__ import annotations

from typing import Any
from pathlib import Path

from je_auto_control.utils.agent_runtime.errors import AgentTaskError
from je_auto_control.utils.agent_runtime.policy import TaskPolicy
from je_auto_control.utils.agent_runtime.target_config import browser_origins
from je_auto_control.utils.agent_runtime.workflow_values import transformed
from je_auto_control.utils.agent_runtime.browser_validation import (
    bounded as _bounded, browser_url_origin as _url_origin,
)


def browser_options(config: dict) -> dict:
    """Require explicit task origins and refuse a desktop-app fallback in a browser draft."""
    if config.get("apps"):
        raise AgentTaskError("browser workflow cannot grant desktop applications")
    return {"backend": "browser", "allowed_origins": browser_origins(config.get("allowed_origins", []))}


def browser_workflow(workflow: str, config: dict, policy: TaskPolicy) -> dict:
    """Build only supported browser workflows without opening a session or starting a task."""
    if workflow == "batch_form":
        return {"actions": _forms(config, policy)}
    if workflow == "transfer":
        return {"actions": _transfer(config, policy)}
    if workflow == "download_archive":
        return _downloads(config, policy)
    raise AgentTaskError("browser backend currently supports batch_form, transfer and download_archive")


def _downloads(config: dict, policy: TaskPolicy) -> dict:
    from je_auto_control.utils.agent_runtime.workflow_specs import _items
    from je_auto_control.utils.agent_runtime.workflow_files import _destination
    from je_auto_control.utils.agent_runtime.browser_transfers import _expected
    directory = policy.path(config.get("directory"))
    entries = _items(config, "files")
    names, actions = [], []
    for index, entry in enumerate(entries):
        if set(entry) - {"name", "sha256", "url", "selector", "frame", "page_url"}:
            raise AgentTaskError("browser download contains unreviewed settings")
        if bool(entry.get("url")) == bool(entry.get("selector")):
            raise AgentTaskError("browser download requires exactly one URL or link selector")
        path = _destination(policy, directory, _text(entry.get("name"), "filename", maximum=255))
        _text(path.name, "filename", maximum=255)
        names.append(path.name)
        actions.append(_navigate(entry.get("page_url", config.get("url")), policy))
        url = entry.get("url")
        if url:
            _navigate(url, policy)  # Validate only; a browser navigation could trigger an ungranted download.
        else:
            variable = f"download_url_{index}"
            actions.append({**_action("AC_browser_link", _locator(entry["selector"], entry.get("frame", ""))),
                            "capture": variable})
            url = {"$capture": variable}
        actions.append(_action("AC_browser_download", {"url": url, "directory": directory, "name": path.name,
                                                       "sha256": _expected(entry.get("sha256", ""))}))
    if len({name.casefold() for name in names}) != len(names):
        raise AgentTaskError("browser archive filenames must be unique")
    manifest = policy.path(config.get("manifest", str(Path(directory) / "manifest.json")))
    actions.append(_action("AC_workflow_manifest", {"directory": directory, "path": manifest, "names": names}))
    return {"actions": actions, "success_criteria": [{"kind": "actions_complete"},
            {"kind": "file_manifest", "path": manifest, "directory": directory, "names": names}]}


def _text(value: Any, name: str, *, empty: bool = False, maximum: int = 8000) -> str:
    _bounded(value, "workflow " + name, maximum, empty=empty)
    return value


def _locator(selector: Any, frame: Any = "") -> dict:
    return {"selector": _text(selector, "selector", maximum=4096),
            "frame": _text(frame, "frame", empty=True, maximum=4096)}


def _action(tool: str, arguments: dict, expected: Any = None) -> dict:
    result = {"tool": tool, "arguments": arguments}
    if expected is not None:
        result["expect_result"] = expected
    return result


def _navigate(url: Any, policy: TaskPolicy) -> dict:
    _text(url, "URL", maximum=4096)
    if _url_origin(url) not in policy.spec.options["allowed_origins"]:
        raise AgentTaskError("browser workflow navigation is outside its reviewed origins")
    return _action("AC_browser_navigate", {"url": url}, True)


def _forms(config: dict, policy: TaskPolicy) -> list[dict]:
    from je_auto_control.utils.agent_runtime.workflow_specs import _items, _rows
    rows, fields = _rows(config, policy), _items(config, "fields")
    if 1 + len(rows) * (len(fields) * 2 + 4) > 1000:
        raise AgentTaskError("browser batch form requires at most one thousand actions")
    actions = [_navigate(config.get("url"), policy)]
    for index, row in enumerate(rows):
        start = len(actions)
        if config.get("new_record_selector"):
            locator = _locator(config["new_record_selector"], config.get("new_record_frame", ""))
            actions.append(_action("AC_browser_click", locator, True))
        for field in fields:
            _form_field(actions, field, row, config)
        confirmation = _row_confirmation(config, row)
        _commit(actions, config, confirmation)
        for action in actions[start:]:
            action["row"] = str(index + 1)
    return actions


def _form_field(actions: list[dict], field: dict, row: dict, config: dict) -> None:
    if set(field) - {"column", "selector", "frame", "transform"} or field.get("column") not in row:
        raise AgentTaskError("browser field requires a mapped table column and reviewed locator")
    locator = _locator(field.get("selector"), field.get("frame", ""))
    if row[field["column"]] is None:
        raise AgentTaskError("browser table field has no supplied value")
    value = transformed(str(row[field["column"]]), field.get("transform", "identity"))
    _text(value, "field value", empty=True)
    actions.append(_action("AC_browser_fill", {**locator, "value": value}, True))
    actions.append(_action("AC_browser_wait", _wait_arguments(config, locator, "value", value), value))


def _row_confirmation(config: dict, row: dict) -> str | None:
    column = config.get("confirmation_column")
    if column is None:
        return None
    if not isinstance(column, str) or column not in row:
        raise AgentTaskError("browser confirmation column is missing from the input table")
    return _text(row[column], "row confirmation")


def _commit(actions: list[dict], config: dict, confirmation: Any = None) -> None:
    expected = _text(confirmation if confirmation is not None else config.get("confirmation_value"), "confirmation")
    locator = _locator(config.get("confirmation_selector"), config.get("confirmation_frame", ""))
    submit = _locator(config.get("submit_selector"), config.get("submit_frame", ""))
    actions.append({**_action("AC_browser_read", {**locator, "operation": "text"}), "expect_not_result": expected})
    actions.append({**_action("AC_browser_click", submit, True), "side_effect": "submit"})
    actions.append(_action("AC_browser_wait", _wait_arguments(config, locator, "text", expected), expected))


def _wait_arguments(config: dict, locator: dict, operation: str, expected: Any) -> dict:
    from je_auto_control.utils.agent_runtime.models import positive
    timeout = config.get("wait_seconds", 5)
    positive(timeout, "browser workflow wait", 60)
    return {**locator, "operation": operation, "expected": expected, "timeout_seconds": timeout}


def _transfer(config: dict, policy: TaskPolicy) -> list[dict]:
    from je_auto_control.utils.agent_runtime.workflow_specs import _items
    fields = _items(config, "fields")
    if len(fields) * 3 + 5 > 1000:
        raise AgentTaskError("browser transfer requires at most one thousand actions")
    actions = [_navigate(config.get("source_url"), policy)]
    for index, field in enumerate(fields):
        _transfer_field(field)
        locator = _locator(field.get("source"), field.get("source_frame", ""))
        actions.append({**_action("AC_browser_read", {**locator, "operation": field.get("source_operation", "value")}),
                        "capture": f"field_{index}"})
    actions.append(_navigate(config.get("destination_url"), policy))
    for index, field in enumerate(fields):
        variable = f"field_{index}"
        captured = {"$capture": variable, "transform": field.get("transform", "identity")}
        locator = _locator(field.get("destination"), field.get("destination_frame", ""))
        actions.append(_action("AC_browser_fill", {**locator, "value": captured}, True))
        actions.append({**_action("AC_browser_wait", _wait_arguments(config, locator, "value", captured)),
                        "expect_capture": variable, "transform": field.get("transform", "identity")})
    _commit(actions, config)
    for action in actions:
        action["row"] = "transfer"
    return actions


def _transfer_field(field: dict) -> None:
    allowed = {"source", "source_frame", "source_operation", "destination", "destination_frame", "transform"}
    if set(field) - allowed or field.get("source_operation", "value") not in {"text", "value"}:
        raise AgentTaskError("browser transfer field contains unreviewed settings")
    transformed("", field.get("transform", "identity"))
