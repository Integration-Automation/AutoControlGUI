"""A focused JSON Schema (Draft 2020-12) validator over parsed JSON.

The framework only ever *generates* JSON Schema (action-lint, tool-use schema)
and ``data_quality.validate_rows`` is a flat, tabular column checker — neither
can validate a nested API request/response body against a real schema. This
adds the missing consumer: validate an in-memory value against a JSON Schema
subset and report every violation with a readable path.

Supported keywords: ``type`` (incl. ``integer`` matching integral floats),
``enum``/``const``, the numeric bounds (``minimum``/``maximum``/
``exclusiveMinimum``/``exclusiveMaximum``/``multipleOf``), the string bounds
(``minLength``/``maxLength``/``pattern``), the array keywords
(``minItems``/``maxItems``/``uniqueItems``/``items``/``prefixItems``/
``contains``), the object keywords (``required``/``minProperties``/
``maxProperties``/``properties``/``patternProperties``/
``additionalProperties``), the combinators (``allOf``/``anyOf``/``oneOf``/
``not``), boolean schemas (``True``/``False``) and local ``$ref``
(``#/$defs/...`` JSON Pointer). Remote ``$ref`` and format assertions are out
of scope.

Pure standard library (``re``); imports no ``PySide6``.
"""
import json
import re
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List

from je_auto_control.utils.exception.exceptions import (
    AutoControlAssertionException, AutoControlJsonException)

Schema = Any  # a dict, or a bool (a boolean schema)


@dataclass(frozen=True)
class SchemaValidationResult:
    """Outcome of validating one value against a schema."""

    ok: bool
    errors: List[Dict[str, str]] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        """Return a plain-dict view for JSON/executor/MCP responses."""
        return {"ok": self.ok, "errors": list(self.errors)}


def _err(path: str, keyword: str, message: str) -> Dict[str, str]:
    return {"path": path, "keyword": keyword, "message": message}


def _is_number(value: Any) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def _is_integer(value: Any) -> bool:
    if isinstance(value, bool):
        return False
    if isinstance(value, int):
        return True
    return isinstance(value, float) and value.is_integer()


_TYPE_CHECKS: Dict[str, Callable[[Any], bool]] = {
    "null": lambda v: v is None,
    "boolean": lambda v: isinstance(v, bool),
    "object": lambda v: isinstance(v, dict),
    "array": lambda v: isinstance(v, list),
    "string": lambda v: isinstance(v, str),
    "number": _is_number,
    "integer": _is_integer,
}


def _json_equal(left: Any, right: Any) -> bool:
    """Equality that keeps ``True``/``1`` and ``False``/``0`` distinct."""
    if isinstance(left, bool) or isinstance(right, bool):
        return left is right
    return left == right


def _is_multiple(value: float, factor: float) -> bool:
    if factor == 0:
        return False
    quotient = value / factor
    return abs(quotient - round(quotient)) < 1e-9


def _has_duplicates(items: List[Any]) -> bool:
    seen = set()
    for item in items:
        key = json.dumps(item, sort_keys=True, default=str)
        if key in seen:
            return True
        seen.add(key)
    return False


# --- keyword checkers (each returns a list of error dicts) ----------------

def _check_type(instance: Any, schema: Dict, path: str, _root: Schema) -> List[Dict]:
    if "type" not in schema:
        return []
    types = schema["type"]
    names = [types] if isinstance(types, str) else types
    if any(_TYPE_CHECKS.get(name, lambda _v: True)(instance) for name in names):
        return []
    return [_err(path, "type", f"expected type {schema['type']}")]


def _check_enum_const(instance: Any, schema: Dict, path: str, _root: Schema) -> List[Dict]:
    errors: List[Dict] = []
    if "const" in schema and not _json_equal(instance, schema["const"]):
        errors.append(_err(path, "const", f"must equal {schema['const']!r}"))
    if "enum" in schema and not any(
            _json_equal(instance, option) for option in schema["enum"]):
        errors.append(_err(path, "enum", f"must be one of {schema['enum']}"))
    return errors


_NUMBER_BOUNDS = (
    ("minimum", lambda v, b: v >= b, "less than minimum"),
    ("maximum", lambda v, b: v <= b, "greater than maximum"),
    ("exclusiveMinimum", lambda v, b: v > b, "not greater than exclusiveMinimum"),
    ("exclusiveMaximum", lambda v, b: v < b, "not less than exclusiveMaximum"),
)


def _check_number(instance: Any, schema: Dict, path: str, _root: Schema) -> List[Dict]:
    if not _is_number(instance):
        return []
    errors: List[Dict] = []
    for key, ok, message in _NUMBER_BOUNDS:
        if key in schema and not ok(instance, schema[key]):
            errors.append(_err(path, key, f"{message} {schema[key]}"))
    if "multipleOf" in schema and not _is_multiple(instance, schema["multipleOf"]):
        errors.append(
            _err(path, "multipleOf", f"not a multiple of {schema['multipleOf']}"))
    return errors


def _check_string(instance: Any, schema: Dict, path: str, _root: Schema) -> List[Dict]:
    if not isinstance(instance, str):
        return []
    errors: List[Dict] = []
    if "minLength" in schema and len(instance) < schema["minLength"]:
        errors.append(_err(path, "minLength", f"shorter than {schema['minLength']}"))
    if "maxLength" in schema and len(instance) > schema["maxLength"]:
        errors.append(_err(path, "maxLength", f"longer than {schema['maxLength']}"))
    if "pattern" in schema and not re.search(schema["pattern"], instance):
        errors.append(_err(path, "pattern", f"does not match /{schema['pattern']}/"))
    return errors


def _array_size_errors(instance: List, schema: Dict, path: str) -> List[Dict]:
    errors: List[Dict] = []
    if "minItems" in schema and len(instance) < schema["minItems"]:
        errors.append(_err(path, "minItems", f"fewer than {schema['minItems']} items"))
    if "maxItems" in schema and len(instance) > schema["maxItems"]:
        errors.append(_err(path, "maxItems", f"more than {schema['maxItems']} items"))
    if schema.get("uniqueItems") and _has_duplicates(instance):
        errors.append(_err(path, "uniqueItems", "items are not unique"))
    return errors


def _array_item_errors(instance: List, schema: Dict, path: str, root: Schema) -> List[Dict]:
    errors: List[Dict] = []
    prefix = schema.get("prefixItems")
    start = 0
    if isinstance(prefix, list):
        for index, subschema in enumerate(prefix[:len(instance)]):
            errors.extend(_validate(instance[index], subschema, f"{path}[{index}]", root))
        start = len(prefix)
    items = schema.get("items")
    if isinstance(items, (dict, bool)):
        for index in range(start, len(instance)):
            errors.extend(_validate(instance[index], items, f"{path}[{index}]", root))
    return errors


def _array_contains_errors(instance: List, schema: Dict, path: str, root: Schema) -> List[Dict]:
    if "contains" not in schema:
        return []
    subschema = schema["contains"]
    if any(not _validate(item, subschema, path, root) for item in instance):
        return []
    return [_err(path, "contains", "no items match the 'contains' schema")]


def _check_array(instance: Any, schema: Dict, path: str, root: Schema) -> List[Dict]:
    if not isinstance(instance, list):
        return []
    errors = _array_size_errors(instance, schema, path)
    errors.extend(_array_item_errors(instance, schema, path, root))
    errors.extend(_array_contains_errors(instance, schema, path, root))
    return errors


def _object_size_required_errors(instance: Dict, schema: Dict, path: str) -> List[Dict]:
    errors: List[Dict] = []
    for key in schema.get("required", []):
        if key not in instance:
            errors.append(_err(path, "required", f"missing required property '{key}'"))
    if "minProperties" in schema and len(instance) < schema["minProperties"]:
        errors.append(
            _err(path, "minProperties", f"fewer than {schema['minProperties']} properties"))
    if "maxProperties" in schema and len(instance) > schema["maxProperties"]:
        errors.append(
            _err(path, "maxProperties", f"more than {schema['maxProperties']} properties"))
    return errors


def _additional_property_errors(value: Any, additional: Any, path: str, root: Schema) -> List[Dict]:
    if additional is None or additional is True:
        return []
    if additional is False:
        return [_err(path, "additionalProperties", "additional property not allowed")]
    return _validate(value, additional, path, root)


def _one_property_errors(key: str, value: Any, schema: Dict, path: str, root: Schema) -> List[Dict]:
    child = f"{path}.{key}"
    matched: List[Schema] = []
    if key in schema.get("properties", {}):
        matched.append(schema["properties"][key])
    matched.extend(
        sub for pattern, sub in schema.get("patternProperties", {}).items()
        if re.search(pattern, key))
    if matched:
        errors: List[Dict] = []
        for subschema in matched:
            errors.extend(_validate(value, subschema, child, root))
        return errors
    return _additional_property_errors(
        value, schema.get("additionalProperties"), child, root)


def _check_object(instance: Any, schema: Dict, path: str, root: Schema) -> List[Dict]:
    if not isinstance(instance, dict):
        return []
    errors = _object_size_required_errors(instance, schema, path)
    for key, value in instance.items():
        errors.extend(_one_property_errors(key, value, schema, path, root))
    return errors


def _check_all_of(instance: Any, schema: Dict, path: str, root: Schema) -> List[Dict]:
    errors: List[Dict] = []
    for subschema in schema.get("allOf", []):
        errors.extend(_validate(instance, subschema, path, root))
    return errors


def _check_any_of(instance: Any, schema: Dict, path: str, root: Schema) -> List[Dict]:
    options = schema.get("anyOf")
    if not options:
        return []
    if any(not _validate(instance, sub, path, root) for sub in options):
        return []
    return [_err(path, "anyOf", "does not match any schema in anyOf")]


def _check_one_of(instance: Any, schema: Dict, path: str, root: Schema) -> List[Dict]:
    options = schema.get("oneOf")
    if not options:
        return []
    matches = sum(1 for sub in options if not _validate(instance, sub, path, root))
    if matches == 1:
        return []
    return [_err(path, "oneOf", f"matched {matches} schemas in oneOf, expected 1")]


def _check_not(instance: Any, schema: Dict, path: str, root: Schema) -> List[Dict]:
    if "not" not in schema:
        return []
    if _validate(instance, schema["not"], path, root):
        return []
    return [_err(path, "not", "must not match the 'not' schema")]


def _check_combinators(instance: Any, schema: Dict, path: str, root: Schema) -> List[Dict]:
    errors = _check_all_of(instance, schema, path, root)
    errors.extend(_check_any_of(instance, schema, path, root))
    errors.extend(_check_one_of(instance, schema, path, root))
    errors.extend(_check_not(instance, schema, path, root))
    return errors


_CHECKERS = (
    _check_type, _check_enum_const, _check_number, _check_string,
    _check_array, _check_object, _check_combinators,
)


def _ref_step(node: Any, token: str, ref: str) -> Any:
    if isinstance(node, dict) and token in node:
        return node[token]
    if isinstance(node, list) and token.isdigit() and int(token) < len(node):
        return node[int(token)]
    raise AutoControlJsonException(f"cannot resolve $ref {ref!r}")


def _resolve_ref(ref: str, root: Schema) -> Schema:
    if not ref.startswith("#"):
        raise AutoControlJsonException(f"only local $ref is supported, got {ref!r}")
    pointer = ref[1:].lstrip("/")
    if not pointer:
        return root
    node = root
    for raw in pointer.split("/"):
        token = raw.replace("~1", "/").replace("~0", "~")
        node = _ref_step(node, token, ref)
    return node


def _resolve_ref_chain(schema: Schema, root: Schema, path: str):
    """Follow chained ``$ref``s to a concrete schema, detecting cycles.

    Returns ``(resolved_schema, None)`` normally, or ``(None, error)`` when the
    ``$ref`` chain loops back on itself (e.g. ``{"$ref": "#"}``) so the caller
    reports a clean schema error instead of hitting ``RecursionError``.
    """
    seen: set = set()
    current = schema
    while isinstance(current, dict) and "$ref" in current:
        ref = current["$ref"]
        if ref in seen:
            return None, _err(path, "$ref", f"cyclic $ref {ref!r}")
        seen.add(ref)
        current = _resolve_ref(ref, root)
    return current, None


def _validate(instance: Any, schema: Schema, path: str, root: Schema) -> List[Dict]:
    if isinstance(schema, dict) and "$ref" in schema:
        schema, ref_error = _resolve_ref_chain(schema, root, path)
        if ref_error is not None:
            return [ref_error]
    if schema is True:
        return []
    if schema is False:
        return [_err(path, "schema", "no value is allowed here")]
    if not isinstance(schema, dict):
        return []
    errors: List[Dict] = []
    for checker in _CHECKERS:
        errors.extend(checker(instance, schema, path, root))
    return errors


def validate_json(instance: Any, schema: Schema) -> SchemaValidationResult:
    """Validate ``instance`` against ``schema``; collect every violation."""
    errors = _validate(instance, schema, "$", schema)
    return SchemaValidationResult(ok=not errors, errors=errors)


def is_valid(instance: Any, schema: Schema) -> bool:
    """Return ``True`` when ``instance`` satisfies ``schema``."""
    return not _validate(instance, schema, "$", schema)


def assert_schema(instance: Any, schema: Schema) -> None:
    """Raise ``AutoControlAssertionException`` if ``instance`` is invalid."""
    result = validate_json(instance, schema)
    if not result.ok:
        summary = "; ".join(f"{e['path']}: {e['message']}" for e in result.errors)
        raise AutoControlAssertionException(
            f"JSON Schema validation failed: {summary}")
