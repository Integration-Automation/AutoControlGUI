"""MSAA bridge for old controls UIA can't model (LegacyIAccessiblePattern)."""
from je_auto_control.utils.legacy_accessible.legacy_accessible import (
    legacy_default_action, legacy_info,
)

__all__ = ["legacy_info", "legacy_default_action"]
