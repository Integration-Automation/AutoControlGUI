"""Compile four reviewed workflows into inspectable, bounded managed-task specifications."""
from __future__ import annotations

import csv
import itertools
import re
import zipfile
from pathlib import Path
from typing import Any, Mapping
from urllib.parse import urlsplit

from je_auto_control.utils.agent_runtime.errors import AgentTaskError
from je_auto_control.utils.agent_runtime.models import AgentTaskSpec, detached
from je_auto_control.utils.agent_runtime.policy import TaskPolicy

WORKFLOWS = ("download_archive", "batch_form", "transfer", "workspace")


def draft_agent_workflow(workflow: str, config: Mapping[str, Any]) -> dict[str, Any]:
    """Preview a deterministic task; this function never submits or operates an application."""
    if workflow not in WORKFLOWS:
        raise AgentTaskError("unknown managed workflow")
    value = detached(config)
    if not isinstance(value, dict):
        raise AgentTaskError("workflow configuration must be an object")
    spec = _base(workflow, value)
    builders = {"download_archive": _downloads, "batch_form": _forms, "transfer": _transfer,
                "workspace": _workspace}
    try:
        spec.update(builders[workflow](value, TaskPolicy(AgentTaskSpec.from_dict(spec))))
    except (KeyError, OSError, TypeError, ValueError, ImportError) as error:
        raise AgentTaskError(f"invalid {workflow} configuration: {type(error).__name__}") from error
    spec["allowed_tools"] = sorted({action["tool"] for action in spec["actions"]})
    spec["budget"] = {"max_steps": max(25, len(spec["actions"]) + 2),
                      "wall_seconds": value.get("wall_seconds", 300),
                      "action_seconds": value.get("action_seconds", 30)}
    validated = AgentTaskSpec.from_dict(spec)
    TaskPolicy(validated)
    _validate_actions(validated)
    return validated.to_dict()


def _base(workflow: str, config: dict) -> dict:
    return {"goal": config.get("goal", workflow.replace("_", " ")), "mode": "skill",
            "target": config.get("target", "local-files" if workflow == "download_archive" else "local-desktop"),
            "roots": config.get("roots", []), "apps": config.get("apps", []),
            "allowed_tools": ["AC_workflow_download"], "success_criteria": [{"kind": "actions_complete"}],
            "actions": [], "options": {"workflow": workflow}}


def _items(config: dict, name: str) -> list[dict]:
    value = config.get(name)
    if not isinstance(value, list) or not value or len(value) > 500:
        raise AgentTaskError(f"{name} requires between 1 and 500 items")
    if not all(isinstance(item, dict) for item in value):
        raise AgentTaskError(f"{name} items must be objects")
    return value


def _action(tool: str, arguments: dict, expected: Any = None) -> dict:
    result = {"tool": tool, "arguments": arguments}
    if expected is not None:
        result["expect_result"] = expected
    return result


def _downloads(config: dict, policy: TaskPolicy) -> dict:
    directory = policy.path(config.get("directory"))
    entries = _items(config, "files")
    from je_auto_control.utils.agent_runtime.workflow_files import _destination
    paths = [_destination(policy, directory, item["name"]) for item in entries]
    if len({str(path).casefold() for path in paths}) != len(paths):
        raise AgentTaskError("archive filenames must be unique")
    for entry in entries:
        if entry.get("sha256") and re.fullmatch(r"[0-9a-f]{64}", entry["sha256"]) is None:
            raise AgentTaskError("sha256 must be 64 lowercase hexadecimal characters")
    origins = sorted({url_origin(item.get("url", "")) for item in entries})
    actions = [_action("AC_workflow_download", {**entry, "directory": directory}) for entry in entries]
    manifest = policy.path(config.get("manifest", str(Path(directory) / "manifest.json")))
    actions.append(_action("AC_workflow_manifest", {"directory": directory, "path": manifest,
                                                  "names": [item["name"] for item in entries]}))
    return {"actions": actions, "options": {"workflow": "download_archive", "allowed_origins": origins}}


def url_origin(url: str) -> str:
    """Require an explicit HTTP(S) origin without embedded credentials or fragments."""
    parsed = urlsplit(url)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname or parsed.username or parsed.password:
        raise AgentTaskError("download URLs require HTTP(S) without embedded credentials")
    if parsed.fragment:
        raise AgentTaskError("download URL fragments are not allowed")
    port = parsed.port or (443 if parsed.scheme == "https" else 80)
    return f"{parsed.scheme}://{parsed.hostname.lower()}:{port}"


def _rows(config: dict, policy: TaskPolicy) -> list[dict]:
    source = Path(policy.path(config.get("source")))
    if source.stat().st_size > 8_000_000:
        raise AgentTaskError("workflow table exceeds eight megabytes")
    if source.suffix.lower() == ".csv":
        with source.open(encoding="utf-8-sig", newline="") as handle:
            rows = list(itertools.islice(csv.DictReader(handle), 501))
    elif source.suffix.lower() == ".xlsx":
        with zipfile.ZipFile(source) as archive:
            if sum(item.file_size for item in archive.infolist()) > 32_000_000:
                raise AgentTaskError("expanded workbook exceeds thirty-two megabytes")
        from je_auto_control.utils.office import read_workbook
        rows = read_workbook(str(source), sheet=config.get("sheet", ""))
    else:
        raise AgentTaskError("batch forms accept CSV or XLSX")
    if not rows or len(rows) > 500:
        raise AgentTaskError("workflow table requires between 1 and 500 rows")
    return rows


def _focus(config: dict) -> dict:
    title = config.get("window_title")
    if not isinstance(title, str) or not title:
        raise AgentTaskError("workflow application requires an explicit window_title")
    return _action("AC_focus_window", {"title_substring": title})


def _forms(config: dict, policy: TaskPolicy) -> dict:
    rows, fields = _rows(config, policy), _items(config, "fields")
    if len(rows) * (len(fields) * 2 + 2) > 1000:
        raise AgentTaskError("batch form requires at most one thousand actions")
    actions = [_focus(config)]
    for index, row in enumerate(rows):
        if any(field.get("column") not in row for field in fields):
            raise AgentTaskError("a mapped column is missing from the input table")
        for field in fields:
            selector = field["selector"]
            value = str(row[field["column"]])
            actions.append(_action("AC_workflow_control", {"operation": "set", "selector": selector,
                                                           "value": value}, True))
            actions.append(_action("AC_workflow_control", {"operation": "get", "selector": selector}, value))
        _commit_actions(actions, config, str(index + 1))
    return {"actions": actions}


def _commit_actions(actions: list[dict], config: dict, row: str) -> None:
    if not config.get("submit_selector") or not config.get("confirmation_selector"):
        raise AgentTaskError("submission requires a button and a read-back confirmation selector")
    if "confirmation_value" not in config:
        raise AgentTaskError("submission requires a deterministic confirmation_value")
    actions.append({**_action("AC_workflow_control", {"operation": "invoke",
                    "selector": config["submit_selector"]}, True), "row": row, "side_effect": "submit"})
    actions.append({**_action("AC_workflow_control", {"operation": "get",
                    "selector": config["confirmation_selector"]}, str(config["confirmation_value"])), "row": row})


def _transfer(config: dict, _policy: TaskPolicy) -> dict:
    actions = [_focus(config["source_app"])]
    fields = _items(config, "fields")
    for index, field in enumerate(fields):
        actions.append({**_action("AC_workflow_control", {"operation": "get", "selector": field["source"]}),
                        "capture": f"field_{index}"})
    actions.append(_focus(config["destination_app"]))
    for index, field in enumerate(fields):
        variable = f"field_{index}"
        captured = {"$capture": variable, "transform": field.get("transform", "identity")}
        actions.append(_action("AC_workflow_control", {"operation": "set", "selector": field["destination"],
                                                        "value": captured}, True))
        actions.append({**_action("AC_workflow_control", {"operation": "get", "selector": field["destination"]}),
                        "expect_capture": variable, "transform": field.get("transform", "identity")})
    _commit_actions(actions, config, "transfer")
    return {"actions": actions}


def _workspace(config: dict, policy: TaskPolicy) -> dict:
    actions = []
    launches = []
    for document in config.get("documents", []):
        path = policy.path(document)
        launches.append(path)
        actions.append(_action("AC_workflow_open", {"path": path}, True))
    for entry in _items(config, "windows"):
        actions.append(_focus(entry))
        if entry.get("position"):
            actions.append(_action("AC_snap_window", {"title": entry["window_title"],
                                                        "position": entry["position"]}, {"moved": True}))
        actions.append(_action("AC_workflow_control", {"operation": "state", "selector": entry["ready_selector"]},
                               entry["ready_state"]))
    return {"actions": actions, "options": {"workflow": "workspace", "approved_documents": launches}}


def _validate_actions(spec: AgentTaskSpec) -> None:
    for action in spec.actions:
        arguments = action["arguments"]
        if action["tool"] == "AC_workflow_control":
            _validate_selector(arguments["selector"], spec.apps)
        if action["tool"] == "AC_snap_window" and arguments["position"] not in {
                "left", "right", "top", "bottom", "top-left", "top-right", "bottom-left", "bottom-right", "max"}:
            raise AgentTaskError("unknown workspace window position")


def _validate_selector(selector: Any, apps: tuple[str, ...]) -> None:
    if not isinstance(selector, Mapping) or set(selector) - {"name", "role", "app_name", "automation_id"}:
        raise AgentTaskError("invalid workflow control selector")
    if not selector.get("name") or not all(isinstance(value, str) for value in selector.values()):
        raise AgentTaskError("workflow controls require a name and text selectors")
    if selector.get("app_name", "").casefold() not in {name.casefold() for name in apps}:
        raise AgentTaskError("workflow selector is outside the application scope")
