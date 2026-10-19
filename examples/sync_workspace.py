"""Capture saved native GUI preferences and explicitly create a separate working copy from an inert generation."""
import json
from pathlib import Path
from tempfile import TemporaryDirectory

from je_auto_control import (
    ConfigSyncError, SyncAdapterState, SyncLocalIdentity, WorkspaceSettingsSyncAdapter, materialize_sync_profile,
)


def main() -> None:
    """Round-trip four whitelisted preferences without Qt imports, network calls or active workspace changes."""
    with TemporaryDirectory(prefix='autocontrol-workspace-sync-') as temporary:
        root = Path(temporary)
        source = root / 'saved-gui.ini'
        source.write_text('[workspace]\ntheme=light\nfont_pt=16\nnavigation_visible=false\nnavigation_width=480\n'
                          '\n[private]\npassword=local-only\n', encoding='utf-8')
        sender = WorkspaceSettingsSyncAdapter(source, SyncAdapterState(root / 'sender.sqlite3',
            SyncLocalIdentity('https://controlled.invalid', 'example', 'desktop')))
        receiver_source = root / 'current-gui.ini'
        receiver = WorkspaceSettingsSyncAdapter(receiver_source, SyncAdapterState(root / 'receiver.sqlite3',
            SyncLocalIdentity('https://controlled.invalid', 'example', 'laptop')))
        report = receiver.apply(sender.snapshot())
        result = materialize_sync_profile([receiver], root / 'profile-cache')
        working_copy = root / 'explicit-workspace.ini'
        working_copy.write_bytes((result.directory / 'workspace.ini').read_bytes())
        # A caller may explicitly pass QSettings(working_copy, IniFormat) to AutoControlGUIUI.
        # The immutable generation itself must remain read-only when the GUI later saves preferences.
        if receiver_source.exists() or b'local-only' in working_copy.read_bytes():
            raise ConfigSyncError('workspace synchronization changed live preferences or exported private data')
        print(json.dumps({'kind': 'workspace', 'stored': report.stored, 'files': result.file_count,
                          'explicit_working_copy': working_copy.name, 'active_preferences_changed': False,
                          'gui_started': False, 'network_calls': 0}))


if __name__ == '__main__':
    main()
