"""Sanitize journal inputs and collect secret values without persisting them."""
import json
import re
from typing import Dict, List, Set, Tuple

from je_auto_control.utils.action_journal.events import JSONValue, safe_payload
from je_auto_control.utils.executor.action_redaction import _confidential_write, is_sensitive_argument

_REFERENCE = re.compile(r'\$\{secrets\.[^{}]+\}')
_MASK = '***'


def _forced(command: str, arguments: object) -> bool:
    return command.startswith('AC_secret_') or _confidential_write([command, arguments])


def private_input(command: str, arguments: object) -> Tuple[JSONValue, List[str]]:
    """Preserve exact secret references; mark masked literals as nonreplayable."""
    payload, reasons = safe_payload(arguments)
    payload, normalized = _serialized_arguments(command, payload)
    reasons.extend(normalized)
    sanitized, masked = _sanitize(command, payload, _forced(command, payload))
    if masked:
        reasons.append('masked secret input requires an explicit secret reference')
    return sanitized, reasons


def _serialized_arguments(command: str, payload: JSONValue) -> Tuple[JSONValue, List[str]]:
    if command != 'AC_execute_journaled' or not isinstance(payload, dict):
        return payload, []
    actions = payload.get('actions')
    if not isinstance(actions, str):
        return payload, []
    try:
        decoded, reasons = safe_payload(json.loads(actions))
    except json.JSONDecodeError:
        decoded, reasons = None, ['serialized actions could not be parsed']
    return {**payload, 'actions': decoded}, reasons


def _private_variable(command: str, arguments: Dict[str, JSONValue]) -> bool:
    name = arguments.get('name')
    if command not in {'AC_set_var', 'AC_get_var'} or not isinstance(name, str):
        return False
    # Dynamic names cannot establish a public classification before the start append.
    return '${' in name or is_sensitive_argument(command, name)


def _private_field(command: str, name: str, forced: bool) -> bool:
    if command == 'AC_write' and name == 'secret':
        return False  # This is the confidentiality flag, not its value.
    if command in {'AC_write', 'AC_write_secret'} and name in {'interval', 'write_interval'}:
        return False
    return forced or is_sensitive_argument(command, name)


def _sanitize(command: str, value: JSONValue, forced: bool) -> Tuple[JSONValue, bool]:
    if isinstance(value, dict):
        return _sanitize_mapping(command, value, forced)
    if isinstance(value, list):
        return _sanitize_sequence(command, value, forced)
    if forced and not (isinstance(value, str) and _REFERENCE.fullmatch(value)):
        return _MASK, True
    return value, False


def _sanitize_mapping(command: str, value: Dict[str, JSONValue], forced: bool) -> Tuple[JSONValue, bool]:
    result: Dict[str, JSONValue] = {}
    masked = False
    private_variable = _private_variable(command, value)
    for name, item in value.items():
        sensitive = _private_field(command, name, forced) or (private_variable and name == 'value')
        result[name], found = _sanitize(command, item, sensitive)
        masked = masked or found
    return result, masked


def _sanitize_sequence(command: str, value: List[JSONValue], forced: bool) -> Tuple[JSONValue, bool]:
    if value and isinstance(value[0], str) and value[0].startswith('AC_'):
        arguments = value[1] if len(value) > 1 else None
        cleaned, reasons = private_input(value[0], arguments)
        return [value[0], cleaned] if len(value) > 1 else [value[0]], bool(reasons)
    values = [_sanitize(command, item, forced) for item in value]
    return [item for item, _ in values], any(masked for _, masked in values)


def secret_values(command: str, raw: object, resolved: object) -> Set[str]:
    """Find confidential resolved strings for later outcome redaction."""
    before, _ = safe_payload(raw)
    after, _ = safe_payload(resolved)
    before, _ = _serialized_arguments(command, before)
    after, _ = _serialized_arguments(command, after)
    return _collect(command, before, after, _forced(command, before))


def _collect(command: str, raw: JSONValue, resolved: JSONValue, forced: bool) -> Set[str]:
    if forced and isinstance(resolved, (bool, int, float)):
        return {str(resolved)}
    if isinstance(raw, str):
        return _collect_text(raw, resolved, forced)
    if isinstance(raw, dict) and isinstance(resolved, dict):
        return _collect_mapping(command, raw, resolved, forced)
    if isinstance(raw, list) and isinstance(resolved, list):
        return _collect_sequence(command, raw, resolved, forced)
    return set()


def _collect_text(raw: str, resolved: JSONValue, forced: bool) -> Set[str]:
    reference = _REFERENCE.search(raw)
    if (forced or reference) and isinstance(resolved, str) and resolved and raw != resolved:
        return {resolved}
    return {raw} if forced and raw and not reference else set()


def _collect_sequence(command: str, raw: List[JSONValue], resolved: List[JSONValue], forced: bool) -> Set[str]:
    if raw and isinstance(raw[0], str) and raw[0].startswith('AC_'):
        before = raw[1] if len(raw) > 1 else None
        after = resolved[1] if len(resolved) > 1 else None
        return _collect(raw[0], before, after, _forced(raw[0], before))
    values: Set[str] = set()
    for before, after in zip(raw, resolved):
        values.update(_collect(command, before, after, forced))
    return values


def _collect_mapping(command: str, raw: Dict[str, JSONValue], resolved: Dict[str, JSONValue],
                     forced: bool) -> Set[str]:
    values: Set[str] = set()
    private_variable = _private_variable(command, raw)
    for name, value in raw.items():
        sensitive = _private_field(command, name, forced) or (private_variable and name == 'value')
        values.update(_collect(command, value, resolved.get(name), sensitive))
    return values


def private_output(command: str, arguments: JSONValue, outcome: JSONValue) -> Tuple[JSONValue, Set[str]]:
    """Mask confidential results; retain sensitive variable strings for later echoes."""
    if command == 'AC_stop_physical_recording':
        # Physical keystrokes are explicit caller output, never an automatic journal artifact.
        return _MASK, set()
    if isinstance(arguments, dict) and _private_variable(command, arguments):
        return _MASK, _output_strings(outcome)
    return outcome, set()


def _output_strings(value: JSONValue) -> Set[str]:
    if isinstance(value, str):
        return {value} if value else set()
    if isinstance(value, (bool, int, float)):
        return {str(value)}
    if isinstance(value, dict):
        result = {key for key in value if key}
        for item in value.values():
            result.update(_output_strings(item))
        return result
    if isinstance(value, list):
        result = set()
        for item in value:
            result.update(_output_strings(item))
        return result
    return set()


def scrub_payload(value: JSONValue, secrets: Set[str], *, redact_fields: bool = True) -> JSONValue:
    """Mask known resolved strings and sensitive mapping fields in outputs."""
    if isinstance(value, str):
        return value if not redact_fields and _REFERENCE.fullmatch(value) else _scrub_text(value, secrets)
    if isinstance(value, list):
        return [scrub_payload(item, secrets, redact_fields=redact_fields) for item in value]
    if isinstance(value, dict):
        return _scrub_mapping(value, secrets, redact_fields)
    return _MASK if value is not None and str(value) in secrets else value


def _scrub_mapping(value: Dict[str, JSONValue], secrets: Set[str], redact_fields: bool) -> JSONValue:
    return {_scrub_text(key, secrets): _MASK if redact_fields and is_sensitive_argument('', key)
            else scrub_payload(item, secrets, redact_fields=redact_fields)
            for key, item in value.items()}


def _scrub_text(text: str, secrets: Set[str]) -> str:
    for secret in sorted(secrets, key=len, reverse=True):
        text = text.replace(secret, _MASK)
    return text
