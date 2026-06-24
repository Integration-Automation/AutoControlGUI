"""Normalise error messages into stable SHA-256 failure signatures + grouping."""
from je_auto_control.utils.failure_signature.failure_signature import (
    failure_signature, group_failures, normalize_error,
)

__all__ = ["normalize_error", "failure_signature", "group_failures"]
