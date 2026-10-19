"""Data-only adapter protocol shared by source capture and inert profile materialization."""
from typing import Iterable, Mapping, Protocol

from je_auto_control.utils.config_sync.adapter_schema import AdapterKind, ApplyReport
from je_auto_control.utils.config_sync.versions import SyncEntry


class SyncAdapter(Protocol):
    """Capture actual sources and persist portable inbox versions without activating synchronized work."""

    @property
    def kind(self) -> AdapterKind:
        """Identify the profile's causal section."""

    def snapshot(self) -> Mapping[str, SyncEntry]:
        """Return current heads, including conflicts, keyed by sealed change ID."""

    def apply(self, entries: Mapping[str, SyncEntry]) -> ApplyReport:
        """Persist validated incoming versions without overwriting the live source."""

    def profile_files(self) -> Mapping[str, bytes]:
        """Return a complete resolved local profile or refuse conflicts/missing references."""

    def resolve(self, entry_id: str, value: dict[str, object], *, observed: Iterable[str],
                  is_deleted: bool = False) -> SyncEntry:
        """Choose a value or tombstone after explicitly reviewing every current head."""

    def definitions(self) -> Mapping[str, dict[str, object]]:
        """Return a complete ready local profile without activating it."""

    def checkpoint(self) -> None:
        """Revalidate the profile's live authority and cancellation while derived files are staged."""
