"""Resolve the hw codec optional group as one outcome."""
from __future__ import annotations

from typing import TYPE_CHECKING as _TYPE_CHECKING, Callable, Protocol


if _TYPE_CHECKING:
    class _InstallHardwareCodec(Protocol):
        def __call__(self, codec_name: str) -> bool:
            ...


def _load() -> tuple[
    Callable[[], list[str]] | None,
    Callable[[], str | None] | None,
    _InstallHardwareCodec | None,
    Callable[[], None] | None,
]:
    try:
        from je_auto_control.utils.remote_desktop.hw_codec import (
            active_hardware_codec, available_hardware_codecs,
            install_hardware_codec, uninstall_hardware_codec,
        )
    except ImportError:
        return (None, None, None, None)
    return (available_hardware_codecs, active_hardware_codec, install_hardware_codec, uninstall_hardware_codec)


available_hardware_codecs, active_hardware_codec, install_hardware_codec, uninstall_hardware_codec = _load()
