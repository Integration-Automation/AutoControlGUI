"""Data profiling and schema inference for AutoControl row-sets."""
from je_auto_control.utils.data_profile.data_profile import (
    infer_schema, profile_rows,
)

__all__ = ["infer_schema", "profile_rows"]
