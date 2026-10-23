"""Create inert managed adapters from host profiles; SDKs and native resources stay lazy."""
from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any

from je_auto_control.utils.agent_runtime.target_config import AgentTargetProfile
from je_auto_control.utils.agent_runtime.errors import AgentTaskError


def build_target(profile: AgentTargetProfile) -> Any:
    """Bind reviewed configuration to a fixed owned helper, never a caller-selected argv."""
    from je_auto_control.utils.agent_runtime.native_target import NativeDesktopTarget
    if profile.kind == "files":
        resource = hashlib.sha256("\n".join(sorted(profile.roots)).encode("utf-8")).hexdigest()
        path = Path.home() / ".je_auto_control" / "input_ownership" / ("files-" + resource + ".lock")
        return NativeDesktopTarget(resource_path=path, recovery_probe=lambda: None, profile=profile.to_dict())
    if profile.kind == "desktop":
        return NativeDesktopTarget(profile=profile.to_dict())
    if profile.kind == "browser":
        path = Path.home() / ".je_auto_control" / "input_ownership" / ("browser-" + profile.digest + ".lock")
        return NativeDesktopTarget(resource_path=path, recovery_probe=lambda: None, profile=profile.to_dict())
    raise AgentTaskError("target kind does not have a host adapter factory")
