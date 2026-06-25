"""Idempotently bring a control or setting to a desired state."""
from je_auto_control.utils.ensure_state.ensure_state import (
    ensure_state, ensure_toggle,
)

__all__ = ["ensure_state", "ensure_toggle"]
