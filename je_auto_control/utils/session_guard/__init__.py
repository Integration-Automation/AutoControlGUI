"""Detect a locked / non-interactive session before driving input."""
from je_auto_control.utils.session_guard.session_guard import (
    ensure_interactive_session, is_session_locked,
)

__all__ = ["ensure_interactive_session", "is_session_locked"]
