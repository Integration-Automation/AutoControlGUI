"""Data-quality helpers for scraped / loaded rows (pure standard library).

``load_rows`` and OCR bring data *in*; this module is the quality gate that
sits between ingestion and downstream entry: validate rows against a
declarative schema, pull structured fields out of free text with named
regex presets, and mask sensitive columns before export.

Pure standard library (``re`` / ``hashlib``); imports no ``PySide6``.
"""
import hashlib
import re
from typing import Any, Dict, List, Optional, Set, cast

_TYPES = {
    "int": int, "float": (int, float), "number": (int, float),
    "str": str, "bool": bool,
}

# Named extraction presets (no capturing groups, so findall returns matches).
_PRESETS = {
    "email": r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}",
    "url": r"https?://[^\s,)]+",
    "ipv4": r"\b(?:\d{1,3}\.){3}\d{1,3}\b",
    "phone": r"\+?\d[\d\s().-]{6,}\d",
    "date_iso": r"\b\d{4}-\d{2}-\d{2}\b",
    "amount": r"[$€£]\s?\d[\d,]*(?:\.\d+)?",
    "hashtag": r"#\w+",
}


# --- row schema validation -----------------------------------------------

def _matches_type(value: Any, kind: str) -> bool:
    expected = _TYPES.get(kind)
    if expected is None:
        return True
    if kind in ("int", "number", "float") and isinstance(value, bool):
        return False
    return isinstance(value, cast(type, expected))


def _number_range_error(value: Any, rule: Dict[str, Any]) -> Optional[str]:
    if "min" in rule and value < rule["min"]:
        return f"below min {rule['min']}"
    if "max" in rule and value > rule["max"]:
        return f"above max {rule['max']}"
    return None


def _length_range_error(value: str, rule: Dict[str, Any]) -> Optional[str]:
    if "min_len" in rule and len(value) < rule["min_len"]:
        return f"shorter than {rule['min_len']}"
    if "max_len" in rule and len(value) > rule["max_len"]:
        return f"longer than {rule['max_len']}"
    return None


def _range_error(value: Any, rule: Dict[str, Any]) -> Optional[str]:
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return _number_range_error(value, rule)
    if isinstance(value, str):
        return _length_range_error(value, rule)
    return None


def _field_error(value: Any, rule: Dict[str, Any]) -> Optional[str]:
    kind = rule.get("type")
    if kind and not _matches_type(value, kind):
        return f"expected {kind}"
    if "regex" in rule and not re.search(rule["regex"], str(value)):
        return f"does not match {rule['regex']}"
    range_msg = _range_error(value, rule)
    if range_msg:
        return range_msg
    allowed = rule.get("allowed")
    if allowed is not None and value not in allowed:
        return "not in allowed set"
    return None


def _validate_row(index: int, row: Dict[str, Any], schema: Dict[str, Any],
                  seen_unique: Dict[str, set]) -> List[Dict[str, Any]]:
    errors: List[Dict[str, Any]] = []
    for field, rule in schema.items():
        if field not in row or row[field] in (None, ""):
            if rule.get("required"):
                errors.append({"row": index, "field": field,
                               "error": "required"})
            continue
        value = row[field]
        message = _field_error(value, rule)
        if message:
            errors.append({"row": index, "field": field, "error": message})
        elif field in seen_unique:
            if value in seen_unique[field]:
                errors.append({"row": index, "field": field,
                               "error": "duplicate"})
            else:
                seen_unique[field].add(value)
    return errors


def validate_rows(rows: List[Dict[str, Any]],
                  schema: Dict[str, Any]) -> Dict[str, Any]:
    """Validate ``rows`` against ``schema``; return a pass/fail report.

    Each schema rule supports ``type`` / ``required`` / ``regex`` /
    ``min`` / ``max`` / ``min_len`` / ``max_len`` / ``allowed`` / ``unique``.
    The report holds ``ok``, ``valid`` / ``invalid`` row lists, and per-row
    ``errors`` (``{row, field, error}``).
    """
    rows = list(rows)
    seen_unique: Dict[str, Set[Any]] = {
        field: set() for field, rule in schema.items()
                   if rule.get("unique")}
    errors: List[Dict[str, Any]] = []
    valid: List[Dict[str, Any]] = []
    invalid: List[Dict[str, Any]] = []
    for index, row in enumerate(rows):
        row_errors = _validate_row(index, row, schema, seen_unique)
        errors.extend(row_errors)
        (invalid if row_errors else valid).append(row)
    return {"ok": not errors, "total": len(rows),
            "valid_count": len(valid), "invalid_count": len(invalid),
            "valid": valid, "invalid": invalid, "errors": errors}


# --- field extraction -----------------------------------------------------

def preset_names() -> List[str]:
    """Return the names of the built-in extraction presets."""
    return sorted(_PRESETS)


def extract_fields(text: str, fields: Optional[List[str]] = None,
                   patterns: Optional[Dict[str, str]] = None
                   ) -> Dict[str, List[str]]:
    """Extract structured values from free text.

    ``fields`` selects built-in presets (default: all); ``patterns`` adds
    or overrides named custom regexes. Returns ``{name: [matches]}``.
    """
    haystack = text or ""
    chosen: Dict[str, str] = {}
    for name in (fields if fields is not None else list(_PRESETS)):
        if name in _PRESETS:
            chosen[name] = _PRESETS[name]
    for name, pattern in (patterns or {}).items():
        chosen[name] = pattern
    return {name: re.findall(pattern, haystack)
            for name, pattern in chosen.items()}


# --- masking --------------------------------------------------------------

def _mask_value(value: str, mode: str) -> str:
    if mode == "redact":
        return "***"
    if mode == "hash":
        return hashlib.sha256(value.encode("utf-8")).hexdigest()
    if mode == "partial":
        return "*" * max(0, len(value) - 4) + value[-4:]
    raise ValueError(f"unknown mask mode: {mode!r}")


def mask_rows(rows: List[Dict[str, Any]],
              rules: Dict[str, str]) -> List[Dict[str, Any]]:
    """Return ``rows`` with masked columns.

    ``rules`` maps a field to a mode: ``redact`` (``***``), ``hash``
    (SHA-256 hex), or ``partial`` (keep last 4 chars).
    """
    masked: List[Dict[str, Any]] = []
    for row in rows:
        out = dict(row)
        for field, mode in rules.items():
            if field in out and out[field] is not None:
                out[field] = _mask_value(str(out[field]), mode)
        masked.append(out)
    return masked
