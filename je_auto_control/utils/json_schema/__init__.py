"""JSON Schema (Draft 2020-12 subset) validation over parsed JSON."""
from je_auto_control.utils.json_schema.json_schema import (
    SchemaValidationResult, assert_schema, is_valid, validate_json,
)

__all__ = [
    "SchemaValidationResult", "assert_schema", "is_valid", "validate_json",
]
