"""One runtime-derived private blob cache never accepts a public path or configuration account selector."""
from __future__ import annotations

from pathlib import Path

from je_auto_control.utils.agent_runtime.errors import AgentTaskError
from je_auto_control.utils.agent_runtime.transfer_models import MAX_TRANSFER_BYTES, _hex
from je_auto_control.utils.config_sync.blob_store import SyncAssetStore


class PrivateTransferCache:
    """Bind cache operations to the owning runtime; the host separately proves each generated account's ownership."""

    def __init__(self, runtime_path: str) -> None:
        runtime = Path(runtime_path)
        self.path = runtime.with_name(runtime.name + '.transfers.sqlite3')
        self.store = SyncAssetStore(self.path, max_bytes=MAX_TRANSFER_BYTES)

    def check(self) -> None:
        """Refuse a cache path or parent which moved through a filesystem link."""
        if self.path.is_symlink() or self.path.resolve() != self.path:
            raise AgentTaskError('private transfer cache path changed')

    def delete_account(self, account: str) -> dict[str, int]:
        """Clean only a host-derived generated account after the caller has fenced its producer."""
        _hex(account, 32)
        self.check()
        return self.store.delete_account(account)
