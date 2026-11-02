"""Strict JSON request adapters with nested path confinement and explicit verification failures."""
from typing import Any, Callable, Optional

from je_auto_control.utils.path_guard.path_guard import validate_path
from je_auto_control.utils.path_guard.policy import PathPolicy
from je_auto_control.utils.self_healing.locator import SelfHealVerificationError, self_heal_run
from je_auto_control.utils.self_healing.requests import SelfHealRequest, SelfHealRequestError, VerificationRequest

_FIELDS = {"template_path", "description", "detect_threshold", "screen_region", "model", "operation",
           "mouse_keycode", "verification", "raise_on_miss"}
_VERIFICATION_FIELDS = {"description", "model", "screen_region"}


def _object(value: object, allowed: set[str]) -> dict[str, Any]:
    if not isinstance(value, dict) or set(value) - allowed:
        raise SelfHealRequestError("request must be an object containing only supported fields")
    return dict(value)


def _bounded_template(path: str, policy: Optional[PathPolicy]) -> str:
    candidate = validate_path(path)
    # pylint: disable-next=import-outside-toplevel  # reason: journal initialization imports the executor adapters
    from je_auto_control.utils.action_journal.capture import _effective_path_policies
    for current in _effective_path_policies(policy):
        candidate = current.validate(candidate, operation="self-healing request template")
    return str(candidate)


def run_json_request(request: dict[str, Any], *, path_policy: Optional[PathPolicy] = None,
                      observer: Optional[Callable[[str], None]] = None) -> dict[str, Any]:
    """Run validated JSON data; callbacks/backends/log objects are Python-only options."""
    values = _object(request, _FIELDS)
    verification = values.pop("verification", None)
    if verification is not None:
        values["verification"] = VerificationRequest(**_object(verification, _VERIFICATION_FIELDS))
    options = SelfHealRequest(**values)
    if options.template_path is not None:
        values["template_path"] = _bounded_template(options.template_path, path_policy)
        options = SelfHealRequest(**values)

    def checkpoint(phase: str) -> None:
        if options.template_path is not None:
            _bounded_template(options.template_path, path_policy)
        if observer is not None:
            observer(phase)
        if options.template_path is not None:
            _bounded_template(options.template_path, path_policy)

    return self_heal_run(options, observer=checkpoint).to_dict()


def _run_self_heal_command(request: dict[str, Any]) -> dict[str, Any]:
    result = run_json_request(request)
    if result.get("verified") is False:
        # Retain the structured result on the typed command error without
        # repeating the operation or verification to construct it.
        raise SelfHealVerificationError(result)
    return result


def request_json_schema() -> dict[str, Any]:
    """Describe the JSON subset, excluding arbitrary Python callbacks and objects."""
    region = {"type": "array", "items": {"type": "integer"}, "minItems": 4, "maxItems": 4}
    verification = {"type": "object", "additionalProperties": False, "required": ["description"],
                    "properties": {"description": {"type": "string", "minLength": 1},
                                   "model": {"type": "string"}, "screen_region": region}}
    return {"type": "object", "additionalProperties": False,
            "properties": {"template_path": {"type": "string", "format": "path"},
                           "description": {"type": "string"},
                           "detect_threshold": {"type": "number", "minimum": 0, "maximum": 1},
                           "screen_region": region, "model": {"type": "string"},
                           "operation": {"type": "string", "enum": ["locate", "click"], "default": "locate"},
                           "mouse_keycode": {"type": "string"}, "verification": verification,
                           "raise_on_miss": {"type": "boolean"}}}
