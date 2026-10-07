"""Observed app state and validated native application identifiers."""
from __future__ import annotations

from dataclasses import dataclass
import re
from typing import Literal

from je_auto_control.wrapper._mobile_models import DeviceSessionError


@dataclass(frozen=True)
class AppState:
    """Observed running state; transport failure raises instead of guessing success."""

    app_id: str
    device_id: str
    state: Literal['running', 'not_running', 'not_installed']
    native_state: int = 0


def validate_app_id(app_id: str) -> None:
    """Reject shell/path syntax before resolving a mobile client."""
    if not isinstance(app_id, str) or not re.fullmatch(r'[A-Za-z][A-Za-z0-9_.-]{0,254}', app_id, re.ASCII):
        raise DeviceSessionError('app_id must be an Android package or iOS bundle identifier')
