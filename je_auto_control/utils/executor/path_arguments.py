"""Apply reviewed filesystem semantics at every scoped executor dispatch."""
from __future__ import annotations

import inspect
from typing import Any, Callable, Dict

from je_auto_control.utils.path_guard.policy import current_path_policy
from je_auto_control.utils.rbac.authorization import current_authorization, require_command

# MCP fields describe wire adapters. These aliases describe their corresponding
# executor parameters, whose public signatures remain unchanged.
_ALIASES = {
    'AC_locate_image_center': ('ac_locate_image_center', {'image_path': 'image'}),
    'AC_locate_and_click': ('ac_locate_and_click', {'image_path': 'image'}),
    'AC_execute_files': ('ac_execute_action_file', {'file_path': 'execute_files_list.*'}),
    'AC_read_action_json': ('ac_read_action_file', {'file_path': 'file_path'}),
    'AC_observe_add': ('ac_observe_add', {'image': 'params.image'}),
}


def _schema_for_command(command: str) -> Dict[str, Any]:
    from je_auto_control.utils.mcp_server.tools._path_metadata import (
        _READ_FIELDS, _WRITE_FIELDS, _mark,
    )
    tool, renames = _ALIASES.get(command, (command.lower(), {}))
    schema: Dict[str, Any] = {'type': 'object'}
    for operation, fields in [('read', _READ_FIELDS), ('write', _WRITE_FIELDS)]:
        for field in fields.get(tool, '').split():
            first, dot, rest = field.partition('.')
            _mark(schema, (renames.get(first, first) + dot + rest).split('.'), operation)
    return schema


def validate_block_arguments(command: str, arguments: Dict[str, Any]) -> Dict[str, Any]:
    """Validate resolved block fields before their handler reads any file."""
    policy = current_path_policy()
    require_command(command, arguments=arguments)
    if policy is None:
        return arguments
    from je_auto_control.utils.mcp_server.tools._path_metadata import validate_path_arguments
    return validate_path_arguments(arguments, _schema_for_command(command), policy)


def validate_event_arguments(command: str, event: Callable[..., Any], value: Any
                             ) -> tuple[tuple[Any, ...], Dict[str, Any]]:
    """Bind resolved args and validate annotated paths, including positional calls.

    No active policy leaves local calls untouched. Defaults are bound before
    validation, so concrete default filenames obey the same root restriction.
    """
    policy = current_path_policy()
    args, kwargs = ((), value) if isinstance(value, dict) else (tuple(value), {})
    if policy is None and current_authorization() is None:
        return args, kwargs
    bound = inspect.signature(event).bind(*args, **kwargs)
    bound.apply_defaults()
    bound.arguments.update(validate_block_arguments(command, dict(bound.arguments)))
    return bound.args, bound.kwargs
