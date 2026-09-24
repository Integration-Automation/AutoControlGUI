"""Tiny shared helper for JSON-dict file persistence (internal plumbing)."""
from je_auto_control.utils.json_store.json_store import (
    SharedJsonDict, read_json_dict, write_json_dict,
)

__all__ = ["SharedJsonDict", "read_json_dict", "write_json_dict"]
