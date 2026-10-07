"""Small, versioned entry points for new integrations.

The historical top-level package remains compatible.  New consumers should
prefer this namespace so importing core automation does not eagerly import
hundreds of optional integrations.
"""

from je_auto_control.utils.remote_desktop.sessions import (
    RemoteSession, SessionStatus, SessionEvent, RemoteSessionError, SessionOwnershipError,
    disconnect_session, get_remote_session, list_remote_session_events,
)
from je_auto_control.api.config_sync import (
    ConfigBucket, ConfigRevisionConflict, ConfigStore, ConfigStoreCapacityError, ConfigSyncError,
    ConfigSyncClient, SyncClientOptions, MergeDecision, PeerState, SyncEntry, can_collect_tombstone, merge_entries,
    OutboxReport, SyncOperation, SyncOutbox, BucketConflict, bucket_peer_states, causal_remove, causal_upsert,
    collect_acknowledged_tombstones, merge_causal_buckets,
)
from je_auto_control.api.codegen import (
    CandidateError, CandidateScript, generate_candidate_from_log, generate_journal_candidate,
)
from je_auto_control.api.journal import (
    ActionEvent, ActionJournal, JournalError, execute_journaled,
    list_journal_runs, read_action_journal, read_events,
)
from je_auto_control.api.healing import (
    EvaluationSample, HealingComparison, HealingEvaluationError, LocatorPrediction,
    LocatorStrategy, TemplateRevisionStore, accept_template_candidate, compare_healing_versions,
    create_template_candidate, evaluate_locators, healing_context, preview_template_candidate,
    revert_template_revision, validate_template_candidate,
)
from je_auto_control.api.mobile import (
    DeviceContext, DeviceSession, DeviceSessionError, open_device, probe_device_contexts,
)
from je_auto_control.api.core import (
    FailureBundleOptions,
    create_failure_bundle,
    execute_action,
    execute_action_with_vars,
    generate_code,
    failure_bundle_on_error,
    run_diagnostics,
)
from je_auto_control.api.wayland_input import (
    InputDevice, InputEvent, PhysicalRecorder, RecordingUnavailable, ShortcutUnavailable,
    StopShortcutSession, WaylandInputSession, start_physical_recording, stop_physical_recording,
    start_wayland_stop_shortcut, stop_wayland_stop_shortcut, wayland_input_status,
)

from je_auto_control.utils.config_sync.adapters import (
    ApplyReport, SyncAdapter, JsonDefinitionAdapter, ScriptSyncAdapter, LocatorSyncAdapter,
    HotkeySyncAdapter, TriggerSyncAdapter, AddressBookSyncAdapter,
)
from je_auto_control.utils.config_sync.assets import (
    AssetSpec, AssetManifest, AssetTransport, AssetSyncResult, AssetSyncError, sync_assets,
)
from je_auto_control.utils.config_sync.service import (
    config_sync_preview, config_sync_exchange, config_sync_apply, config_sync_retry, config_sync_status,
)
from je_auto_control.utils.config_sync.asset_service import config_sync_assets


__all__ = [
    'DeviceContext', 'DeviceSession', 'DeviceSessionError', 'open_device', 'probe_device_contexts',
    'InputDevice', 'InputEvent', 'PhysicalRecorder', 'RecordingUnavailable', 'ShortcutUnavailable',
    'StopShortcutSession', 'WaylandInputSession', 'start_physical_recording', 'stop_physical_recording',
    'start_wayland_stop_shortcut', 'stop_wayland_stop_shortcut', 'wayland_input_status',
    'RemoteSession', 'SessionStatus', 'SessionEvent', 'RemoteSessionError', 'SessionOwnershipError',
    'disconnect_session', 'get_remote_session', 'list_remote_session_events',

    'ApplyReport', 'SyncAdapter', 'JsonDefinitionAdapter', 'ScriptSyncAdapter', 'LocatorSyncAdapter',
    'HotkeySyncAdapter', 'TriggerSyncAdapter', 'AddressBookSyncAdapter', 'AssetSpec', 'AssetManifest',
    'AssetTransport', 'AssetSyncResult', 'AssetSyncError', 'sync_assets', 'config_sync_preview',
    'config_sync_exchange', 'config_sync_apply', 'config_sync_retry', 'config_sync_status', 'config_sync_assets',

    'ConfigBucket', 'ConfigRevisionConflict', 'ConfigStore', 'ConfigStoreCapacityError', 'ConfigSyncError',
    'ConfigSyncClient', 'SyncClientOptions', 'MergeDecision', 'PeerState', 'SyncEntry', 'can_collect_tombstone',
    'merge_entries', 'OutboxReport', 'SyncOperation', 'SyncOutbox', 'BucketConflict', 'bucket_peer_states',
    'causal_remove', 'causal_upsert', 'collect_acknowledged_tombstones', 'merge_causal_buckets',
    'CandidateError', 'CandidateScript', 'generate_candidate_from_log', 'generate_journal_candidate',
    "FailureBundleOptions", "create_failure_bundle", "execute_action",
    "execute_action_with_vars", "failure_bundle_on_error", "generate_code",
    "run_diagnostics", "ActionEvent", "ActionJournal", "JournalError",
    "execute_journaled", "list_journal_runs", "read_action_journal", "read_events",
    "EvaluationSample", "HealingComparison", "HealingEvaluationError", "LocatorPrediction",
    "LocatorStrategy", "TemplateRevisionStore", "accept_template_candidate", "compare_healing_versions",
    "create_template_candidate", "evaluate_locators", "healing_context", "preview_template_candidate",
    "revert_template_revision", "validate_template_candidate",
]
