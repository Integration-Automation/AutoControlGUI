"""JSON-Schema compatibility classification for AutoControl."""
from je_auto_control.utils.schema_compat.schema_compat import (
    SchemaChange, check_compatibility, diff_schemas, is_backward_compatible,
    is_forward_compatible, is_full_compatible,
)

__all__ = [
    "SchemaChange", "check_compatibility", "diff_schemas",
    "is_backward_compatible", "is_forward_compatible", "is_full_compatible",
]
