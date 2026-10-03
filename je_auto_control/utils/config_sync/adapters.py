"""Shared portable definition interfaces and concrete definition-only store adapters."""
from .definition_adapter import ApplyReport, JsonDefinitionAdapter, LocatorSyncAdapter, ScriptSyncAdapter, SyncAdapter
from .runtime_adapters import AddressBookSyncAdapter, HotkeySyncAdapter, TriggerSyncAdapter

__all__ = ['ApplyReport', 'SyncAdapter', 'JsonDefinitionAdapter', 'ScriptSyncAdapter', 'LocatorSyncAdapter',
           'AddressBookSyncAdapter', 'HotkeySyncAdapter', 'TriggerSyncAdapter']
