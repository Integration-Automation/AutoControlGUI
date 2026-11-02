"""Resolve the mic uplink optional group as one outcome."""
from __future__ import annotations

from typing import TYPE_CHECKING as _TYPE_CHECKING


if _TYPE_CHECKING:
    from je_auto_control.utils.remote_desktop.webrtc_mic import (
        MicUplinkReceiver as _MicUplinkReceiver,
        MicUplinkSender as _MicUplinkSender,
    )


def _load() -> tuple[type[_MicUplinkSender] | None, type[_MicUplinkReceiver] | None]:
    try:
        from je_auto_control.utils.remote_desktop.webrtc_mic import MicUplinkReceiver, MicUplinkSender
    except ImportError:
        return (None, None)
    return (MicUplinkSender, MicUplinkReceiver)


MicUplinkSender, MicUplinkReceiver = _load()
