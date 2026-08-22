"""Standards-based JSON Pointer / Patch / Merge Patch over parsed JSON.

``jsonpath`` queries (read-only) and ``approval`` compares whole artifacts by
equality, but nothing could address a single location, compute a structured
delta, or apply a partial update to a JSON document. This adds the three IETF
primitives that fill that gap:

* **RFC 6901 JSON Pointer** — address one location (``/a/b/0``).
* **RFC 6902 JSON Patch** — an ordered op list (add/remove/replace/move/copy/
  test); plus ``make_patch`` to diff two documents.
* **RFC 7386 JSON Merge Patch** — a recursive merge where ``null`` deletes.

Useful for config-drift detection, partial updates in flows, HTTP PATCH bodies,
and reporting golden-master deltas. Pure standard library (``json`` + ``copy``);
fully deterministic; imports no ``PySide6``.
"""
import copy
from typing import Any, Dict, List

from je_auto_control.utils.exception.exceptions import AutoControlException

_MISSING = object()


class PatchError(AutoControlException):
    """A JSON Patch could not be applied."""


class PatchTestFailed(PatchError):
    """A JSON Patch ``test`` operation did not match."""


# --- RFC 6901 JSON Pointer -------------------------------------------------

def _unescape(ref: str) -> str:
    return ref.replace("~1", "/").replace("~0", "~")


def escape_token(ref: str) -> str:
    """Escape a single reference token for use in a JSON Pointer."""
    return ref.replace("~", "~0").replace("/", "~1")


def _split_pointer(pointer: str) -> List[str]:
    if pointer == "":
        return []
    if not pointer.startswith("/"):
        raise PatchError(f"invalid JSON Pointer {pointer!r}")
    refs: List[str] = []
    for ref in pointer.split("/")[1:]:
        refs.append(_unescape(ref))
    return refs


def _array_index(ref: str, length: int, *, allow_end: bool = False) -> int:
    if ref == "-":
        if allow_end:
            return length
        raise PatchError("array index '-' is not valid here")
    if not ref.isdigit() or (len(ref) > 1 and ref[0] == "0"):
        raise PatchError(f"invalid array index {ref!r}")
    index = int(ref)
    if index >= length:
        raise PatchError(f"array index {index} out of range")
    return index


def _child(node: Any, ref: str) -> Any:
    if isinstance(node, dict):
        if ref in node:
            return node[ref]
        raise PatchError(f"object has no key {ref!r}")
    if isinstance(node, list):
        return node[_array_index(ref, len(node))]
    raise PatchError(f"cannot descend into {type(node).__name__}")


def _walk(node: Any, refs: List[str]) -> Any:
    for ref in refs:
        node = _child(node, ref)
    return node


def resolve_pointer(doc: Any, pointer: str, default: Any = _MISSING) -> Any:
    """Return the value ``pointer`` addresses in ``doc`` (RFC 6901)."""
    try:
        return _walk(doc, _split_pointer(pointer))
    except PatchError:
        if default is not _MISSING:
            return default
        raise


def set_pointer(doc: Any, pointer: str, value: Any) -> Any:
    """Return a copy of ``doc`` with ``pointer`` set to ``value``."""
    if pointer == "":
        return copy.deepcopy(value)
    refs = _split_pointer(pointer)
    result = copy.deepcopy(doc)
    parent = _walk(result, refs[:-1])
    _assign(parent, refs[-1], value, insert=False)
    return result


def remove_pointer(doc: Any, pointer: str) -> Any:
    """Return a copy of ``doc`` with the value at ``pointer`` removed."""
    if pointer == "":
        raise PatchError("cannot remove the whole document")
    refs = _split_pointer(pointer)
    result = copy.deepcopy(doc)
    _delete(_walk(result, refs[:-1]), refs[-1])
    return result


def _assign(parent: Any, ref: str, value: Any, *, insert: bool) -> None:
    if isinstance(parent, dict):
        parent[ref] = value
    elif isinstance(parent, list):
        index = _array_index(ref, len(parent), allow_end=True)
        if insert:
            parent.insert(index, value)
        elif index == len(parent):
            parent.append(value)
        else:
            parent[index] = value
    else:
        raise PatchError(f"cannot set into {type(parent).__name__}")


def _delete(parent: Any, ref: str) -> None:
    if isinstance(parent, dict):
        if ref not in parent:
            raise PatchError(f"object has no key {ref!r}")
        del parent[ref]
    elif isinstance(parent, list):
        del parent[_array_index(ref, len(parent))]
    else:
        raise PatchError(f"cannot remove from {type(parent).__name__}")


# --- equality (bool stays distinct from int) -------------------------------

def _dict_equal(left: Dict, right: Dict) -> bool:
    return left.keys() == right.keys() and all(
        _json_equal(left[key], right[key]) for key in left)


def _list_equal(left: List, right: List) -> bool:
    return len(left) == len(right) and all(
        _json_equal(a, b) for a, b in zip(left, right))


def _json_equal(left: Any, right: Any) -> bool:
    if isinstance(left, bool) or isinstance(right, bool):
        return left is right
    if isinstance(left, dict) and isinstance(right, dict):
        return _dict_equal(left, right)
    if isinstance(left, list) and isinstance(right, list):
        return _list_equal(left, right)
    return left == right


# --- RFC 6902 JSON Patch ---------------------------------------------------

def _op_add(doc: Any, op: Dict[str, Any]) -> Any:
    refs = _split_pointer(op["path"])
    if not refs:
        return copy.deepcopy(op["value"])
    _assign(_walk(doc, refs[:-1]), refs[-1], op["value"], insert=True)
    return doc


def _op_remove(doc: Any, op: Dict[str, Any]) -> Any:
    refs = _split_pointer(op["path"])
    if not refs:
        raise PatchError("cannot remove the whole document")
    _delete(_walk(doc, refs[:-1]), refs[-1])
    return doc


def _op_replace(doc: Any, op: Dict[str, Any]) -> Any:
    refs = _split_pointer(op["path"])
    if not refs:
        return copy.deepcopy(op["value"])
    parent = _walk(doc, refs[:-1])
    _child(parent, refs[-1])  # must exist
    _assign(parent, refs[-1], op["value"], insert=False)
    return doc


def _is_prefix(prefix: str, pointer: str) -> bool:
    head = _split_pointer(prefix)
    full = _split_pointer(pointer)
    return len(head) < len(full) and full[:len(head)] == head


def _op_move(doc: Any, op: Dict[str, Any]) -> Any:
    source, dest = op["from"], op["path"]
    if source == dest:
        return doc
    if _is_prefix(source, dest):
        raise PatchError("cannot move a value into its own child")
    value = resolve_pointer(doc, source)
    doc = _op_remove(doc, {"path": source})
    return _op_add(doc, {"path": dest, "value": value})


def _op_copy(doc: Any, op: Dict[str, Any]) -> Any:
    value = copy.deepcopy(resolve_pointer(doc, op["from"]))
    return _op_add(doc, {"path": op["path"], "value": value})


def _op_test(doc: Any, op: Dict[str, Any]) -> Any:
    actual = resolve_pointer(doc, op["path"], default=_MISSING)
    if actual is _MISSING or not _json_equal(actual, op["value"]):
        raise PatchTestFailed(f"test failed at {op['path']!r}")
    return doc


_OPS = {
    "add": _op_add, "remove": _op_remove, "replace": _op_replace,
    "move": _op_move, "copy": _op_copy, "test": _op_test,
}


def apply_patch(doc: Any, patch: List[Dict[str, Any]]) -> Any:
    """Apply an RFC 6902 patch to ``doc`` atomically; return the new document."""
    result = copy.deepcopy(doc)
    for op in patch:
        handler = _OPS.get(str(op.get("op", "")))
        if handler is None:
            raise PatchError(f"unknown patch op {op.get('op')!r}")
        result = handler(result, op)
    return result


def _diff_dict(old: Dict, new: Dict, path: str) -> List[Dict[str, Any]]:
    ops: List[Dict[str, Any]] = []
    for key in old:
        if key not in new:
            ops.append({"op": "remove", "path": f"{path}/{escape_token(key)}"})
    for key, value in new.items():
        child = f"{path}/{escape_token(key)}"
        if key not in old:
            ops.append({"op": "add", "path": child, "value": value})
        else:
            ops.extend(make_patch(old[key], value, child))
    return ops


def _diff_list(old: List, new: List, path: str) -> List[Dict[str, Any]]:
    ops: List[Dict[str, Any]] = []
    for index in range(min(len(old), len(new))):
        ops.extend(make_patch(old[index], new[index], f"{path}/{index}"))
    for index in range(len(old) - 1, len(new) - 1, -1):
        ops.append({"op": "remove", "path": f"{path}/{index}"})
    for index in range(len(old), len(new)):
        ops.append({"op": "add", "path": f"{path}/-", "value": new[index]})
    return ops


def make_patch(old: Any, new: Any, path: str = "") -> List[Dict[str, Any]]:
    """Return an RFC 6902 patch that turns ``old`` into ``new``."""
    if _json_equal(old, new):
        return []
    if isinstance(old, dict) and isinstance(new, dict):
        return _diff_dict(old, new, path)
    if isinstance(old, list) and isinstance(new, list):
        return _diff_list(old, new, path)
    return [{"op": "replace", "path": path, "value": new}]


# --- RFC 7386 JSON Merge Patch ---------------------------------------------

def merge_patch(doc: Any, patch: Any) -> Any:
    """Apply an RFC 7386 merge patch (``null`` deletes a key)."""
    if not isinstance(patch, dict):
        return copy.deepcopy(patch)
    result = copy.deepcopy(doc) if isinstance(doc, dict) else {}
    for key, value in patch.items():
        if value is None:
            result.pop(key, None)
        else:
            result[key] = merge_patch(result.get(key), value)
    return result


def make_merge_patch(old: Any, new: Any) -> Any:
    """Return an RFC 7386 merge patch turning ``old`` into ``new``."""
    if not (isinstance(old, dict) and isinstance(new, dict)):
        return copy.deepcopy(new)
    patch: Dict[str, Any] = {}
    for key in old:
        if key not in new:
            patch[key] = None
    for key, value in new.items():
        if key not in old:
            patch[key] = copy.deepcopy(value)
        elif not _json_equal(old[key], value):
            patch[key] = make_merge_patch(old[key], value)
    return patch
