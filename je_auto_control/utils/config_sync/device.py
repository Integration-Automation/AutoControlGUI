"""This machine's identity in config sync.

Version vectors count changes per device id, so every machine needs one that
is stable across restarts and never shared with another machine. It is
created on first use and kept in a small file under the user's home.

Pure standard library; imports no ``PySide6``.
"""
from __future__ import annotations

import socket
import uuid
from pathlib import Path

from je_auto_control.utils.config_sync.bucket import ConfigSyncError


def default_device_id_path() -> Path:
    """``~/.je_auto_control/config_sync_device_id``, resolved at call time."""
    return Path.home() / ".je_auto_control" / "config_sync_device_id"


def default_device_id() -> str:
    """This machine's stable sync id, created on first use.

    Version vectors count changes per device id, so two machines must never
    share one; the id is the host name plus a random suffix, kept in
    :func:`default_device_id_path`.
    """
    from je_auto_control.utils.json_store.json_store import atomic_write_text
    path = default_device_id_path()
    try:
        known = path.read_text(encoding="utf-8").strip()
    except OSError:
        known = ""
    if known:
        return known
    device_id = f"{socket.gethostname() or 'device'}-{uuid.uuid4().hex[:12]}"
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        atomic_write_text(path, device_id + "\n")
    except OSError as error:
        raise ConfigSyncError(f"cannot store this device's sync id at {path}: {error}") from error
    return device_id


__all__ = ["default_device_id", "default_device_id_path"]
