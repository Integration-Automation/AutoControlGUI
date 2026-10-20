"""Load seven native profile domains and a real image into independent working copies without running or arming work."""
from hashlib import sha256
import json
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import cast

from examples.sync_referenced_assets import _template_png
from je_auto_control import LoadedSyncProfile, SyncReference, SyncWorkspace, load_sync_profile


def configuration(root: Path) -> dict[str, object]:
    """Select seven temporary native definition domains and bind one explicit image asset."""
    image = root / 'selected-template.png'
    image.write_bytes(_template_png())
    definitions: dict[str, object] = {
        'scripts': {'demo.json': {'actions': [['AC_locate_image_center', {'image': str(image)}]]}},
        'locators': {'login': {'name': 'Sign in', 'role': 'button'}},
        'hotkeys': {'demo-key': {'combo': 'ctrl+alt+1', 'script_path': 'scripts/demo.json'}},
        'triggers': {'demo-watch': {'kind': 'file', 'script_path': 'scripts/demo.json', 'repeat': False,
                                   'cooldown_seconds': 1, 'condition': {'watch_path': 'assets/watched.txt'}}},
        'address_book': [{'host_id': 'example-host', 'server_url': 'https://relay.invalid', 'label': 'Example',
                          'favorite': False, 'tags': ['example']}],
        'settings': {'example': {'value': 'working copy'}},
        'workspace': {'theme': {'value': 'light'}, 'navigation_visible': {'value': False}},
    }
    profiles: list[dict[str, object]] = [
        {'kind': kind, 'state_path': str(root / 'adapters.sqlite3'), 'source': {'records': values}}
        for kind, values in definitions.items()]
    profiles[0]['bindings'] = {
        'fields': {'demo.json': {'/actions/0/1/image': SyncReference('local', 'button').to_dict()}},
        'local_values': {'button': str(image)}, 'assets': {'button': 'assets/template.png'}}
    return {'schema_version': 1, 'endpoint': 'https://controlled.invalid', 'user_id': 'example',
            'outbox_path': str(root / 'outbox.sqlite3'), 'profiles': profiles}


def workflow(root: Path) -> dict[str, object]:
    """Capture, publish and explicitly load native working data using temporary files only."""
    workspace = SyncWorkspace(configuration(root))
    workspace.capture()
    generation = workspace.materialize(root / 'immutable-cache')
    original = _digests(generation.directory)
    loaded: LoadedSyncProfile = load_sync_profile(generation.directory, root / 'workspaces',
                                                   expected_digest=generation.manifest_digest)
    actions = loaded.script_actions('demo.json')
    arguments = cast(dict[str, object], cast(list[object], actions[0])[1])
    assert arguments['image'] == str(loaded.directory / 'assets/template.png')
    assert loaded.hotkeys[0].enabled is False and loaded.triggers[0].enabled is False
    assert loaded.address_book.list_entries()[0]['host_id'] == 'example-host'
    loaded.locators.save('cancel', name='Cancel')
    assert 'cancel' in loaded.locators.all()
    assert original == _digests(generation.directory)
    return dict(loaded.to_dict(), immutable_source_unchanged=True, executed=0, listeners_started=0,
                external_calls=0, image_bytes=(loaded.directory / 'assets/template.png').stat().st_size)


def _digests(directory: Path) -> dict[str, str]:
    return {path.relative_to(directory).as_posix(): sha256(path.read_bytes()).hexdigest()
            for path in directory.rglob('*') if path.is_file()}


def main() -> None:
    """Demonstrate an explicit native working copy without network, device or paid API access."""
    with TemporaryDirectory(prefix='autocontrol-native-profile-') as temporary:
        print(json.dumps(workflow(Path(temporary)), ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
