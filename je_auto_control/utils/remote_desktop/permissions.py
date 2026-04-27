"""Granular per-session permissions for the WebRTC host.

Replaces the single ``read_only`` flag with independent toggles. Defaults
match the prior behavior (everything allowed) so existing call sites
don't change behavior unless they opt in.

The existing ``read_only=True`` flag on :class:`WebRTCDesktopHost` is now
shorthand for ``allow_input=False, allow_clipboard=False, allow_files=False``;
``read_only=False`` leaves permissions at the default-all-true.
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass
class SessionPermissions:
    """What a single connected viewer is allowed to do.

    ``allow_view`` and ``allow_audio`` apply to the streams the host
    publishes (skip the video/audio track when False). ``allow_input``,
    ``allow_clipboard``, ``allow_files`` gate the corresponding inbound
    DataChannel message types.
    """
    allow_view: bool = True
    allow_audio: bool = True
    allow_input: bool = True
    allow_clipboard: bool = True
    allow_files: bool = True

    @classmethod
    def view_only(cls) -> "SessionPermissions":
        """Eyes-only: viewer sees but cannot touch."""
        return cls(
            allow_view=True, allow_audio=True,
            allow_input=False, allow_clipboard=False, allow_files=False,
        )

    @classmethod
    def full_control(cls) -> "SessionPermissions":
        return cls()

    @classmethod
    def none(cls) -> "SessionPermissions":
        return cls(
            allow_view=False, allow_audio=False, allow_input=False,
            allow_clipboard=False, allow_files=False,
        )

    @classmethod
    def from_read_only(cls, read_only: bool) -> "SessionPermissions":
        return cls.view_only() if read_only else cls.full_control()

    def to_dict(self) -> dict:
        return {
            "allow_view": self.allow_view,
            "allow_audio": self.allow_audio,
            "allow_input": self.allow_input,
            "allow_clipboard": self.allow_clipboard,
            "allow_files": self.allow_files,
        }


__all__ = ["SessionPermissions"]
