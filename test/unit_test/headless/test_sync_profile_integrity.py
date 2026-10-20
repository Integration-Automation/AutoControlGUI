"""Native working copies require complete reviewed bytes, sealed definitions and late cancellation/root checks."""
from concurrent.futures import CancelledError
from hashlib import sha256
import json
from pathlib import Path
from threading import Event

import pytest

from headless.test_sync_profile_load import materialized, profiles
import je_auto_control as ac
from je_auto_control.utils.config_sync import profile_load
from je_auto_control.utils.config_sync.adapter_commands import _materialize_sync_profile
from je_auto_control.utils.config_sync.adapter_factory import adapter_from_profile
from je_auto_control.utils.config_sync.contract import _encoded
from je_auto_control.utils.exception.exceptions import AutoControlException


def reseal(result, changes):
    directory = Path(result['directory'])
    old = ac.AssetManifest.from_dict(json.loads((directory.parent / 'manifest.json').read_text(encoding='utf-8')))
    assets = {item.path: item for item in old.files}
    for name, body in changes.items():
        (directory / name).parent.mkdir(parents=True, exist_ok=True)
        (directory / name).write_bytes(body)
        assets[name] = ac.AssetFile(name, sha256(body).hexdigest(), len(body))
    manifest = ac.AssetManifest(tuple(assets.values()))
    (directory.parent / 'manifest.json').write_text(_encoded(manifest.to_dict()), encoding='ascii')
    return manifest.digest


def no_workspace(tmp_path):
    target = tmp_path / 'workspaces'
    assert not list(target.iterdir()) if target.exists() else True


def test_only_explicit_assets_rebase_while_literals_and_secret_placeholders_keep_their_meaning(tmp_path, monkeypatch):
    monkeypatch.setenv('AUTOCONTROL_ALLOWED_PATH_ROOTS', str(tmp_path))
    image = tmp_path / 'button.bin'
    image.write_bytes(b'complete opaque image bytes')
    profile = profiles(tmp_path)[0]
    profile['source']['records']['demo.json'] = {'actions': [['AC_example', {
        'image': str(image), 'label': 'assets/button.bin', 'password': 'private-source-only'}]]}
    profile['bindings'] = {'fields': {'demo.json': {
        '/actions/0/1/image': ac.SyncReference('local', 'button').to_dict(),
        '/actions/0/1/password': ac.SyncReference('secret', 'LOGIN').to_dict()}},
        'local_values': {'button': str(image)}, 'assets': {'button': 'assets/button.bin'}}
    adapter_from_profile(profile).snapshot()
    result = _materialize_sync_profile([profile], str(tmp_path / 'cache'))
    loaded = ac.load_sync_profile(result['directory'], tmp_path / 'workspaces',
                                  expected_digest=result['manifest_digest'])
    arguments = loaded.script_actions('demo.json')[0][1]
    assert arguments['image'] == str(loaded.directory / 'assets/button.bin')
    assert arguments['label'] == 'assets/button.bin' and arguments['password'] == '${secrets.LOGIN}'
    assert (loaded.directory / 'assets/button.bin').read_bytes() == image.read_bytes()
    source = json.loads((Path(result['directory']) / 'scripts/demo.json').read_text(encoding='utf-8'))
    assert source[0][1]['image'] == 'assets/button.bin'
    assert 'private-source-only' not in json.dumps(loaded.script_actions('demo.json'))


@pytest.mark.parametrize('case', ['hotkey_enabled', 'child_enabled', 'literal_changed', 'unreferenced'])
def test_resealed_hashes_cannot_bypass_native_disable_or_head_consistency(tmp_path, monkeypatch, case):
    monkeypatch.setenv('AUTOCONTROL_ALLOWED_PATH_ROOTS', str(tmp_path))
    result = materialized(tmp_path)
    root = Path(result['directory'])
    if case == 'unreferenced':
        changes = {'extra.json': b'{}'}
    else:
        name = {'hotkey_enabled': 'hotkeys.json', 'child_enabled': 'triggers.json',
                'literal_changed': 'scripts/demo.json'}[case]
        value = json.loads((root / name).read_text(encoding='utf-8'))
        if case == 'hotkey_enabled':
            value['hotkeys'][0]['enabled'] = True
        elif case == 'child_enabled':
            value['triggers'][0]['children'][0]['enabled'] = True
        else:
            value[0][1]['message'] = 'unreviewed edit'
        changes = {name: json.dumps(value, sort_keys=True, separators=(',', ':')).encode('ascii')}
    digest = reseal(result, changes)
    with pytest.raises(ac.ConfigSyncError):
        ac.load_sync_profile(root, tmp_path / 'workspaces', expected_digest=digest)
    no_workspace(tmp_path)


def test_root_revocation_during_verified_copy_cleans_its_owned_staging_directory(tmp_path, monkeypatch):
    monkeypatch.setenv('AUTOCONTROL_ALLOWED_PATH_ROOTS', str(tmp_path))
    result = materialized(tmp_path)
    copy = profile_load._copy_stream

    def revoke(*args, **kwargs):
        copy(*args, **kwargs)
        monkeypatch.setenv('AUTOCONTROL_ALLOWED_PATH_ROOTS', str(tmp_path / 'different-root'))

    monkeypatch.setattr(profile_load, '_copy_stream', revoke)
    with pytest.raises(AutoControlException):
        ac.load_sync_profile(result['directory'], tmp_path / 'workspaces', expected_digest=result['manifest_digest'])
    no_workspace(tmp_path)


def test_mid_copy_stop_cannot_leave_a_complete_or_partial_working_profile(tmp_path, monkeypatch):
    monkeypatch.setenv('AUTOCONTROL_ALLOWED_PATH_ROOTS', str(tmp_path))
    result = materialized(tmp_path)
    stop = Event()
    copy = profile_load._copy_stream

    def cancel(*args, **kwargs):
        copy(*args, **kwargs)
        stop.set()

    monkeypatch.setattr(profile_load, '_copy_stream', cancel)
    with pytest.raises(CancelledError):
        ac.load_sync_profile(result['directory'], tmp_path / 'workspaces',
                             expected_digest=result['manifest_digest'], cancelled=stop.is_set)
    no_workspace(tmp_path)


def test_stop_after_atomic_publication_does_not_claim_the_working_copy_was_rolled_back(tmp_path, monkeypatch):
    monkeypatch.setenv('AUTOCONTROL_ALLOWED_PATH_ROOTS', str(tmp_path))
    result = materialized(tmp_path)
    stop = Event()
    rename = Path.rename

    def committed(path, target):
        value = rename(path, target)
        if Path(target).name.startswith('workspace-'):
            stop.set()
        return value

    monkeypatch.setattr(Path, 'rename', committed)
    loaded = ac.load_sync_profile(result['directory'], tmp_path / 'workspaces',
                                  expected_digest=result['manifest_digest'], cancelled=stop.is_set)
    assert stop.is_set() and loaded.directory.is_dir()
    assert loaded.hotkeys[0].enabled is False and loaded.triggers[0].enabled is False


def test_a_working_copy_cannot_be_published_inside_its_immutable_source(tmp_path, monkeypatch):
    monkeypatch.setenv('AUTOCONTROL_ALLOWED_PATH_ROOTS', str(tmp_path))
    result = materialized(tmp_path)
    root = Path(result['directory'])
    with pytest.raises(ac.ConfigSyncError):
        ac.load_sync_profile(root, root / 'working', expected_digest=result['manifest_digest'])
    assert not (root / 'working').exists()


def test_source_replacement_after_review_is_rechecked_while_staging_bytes(tmp_path, monkeypatch):
    monkeypatch.setenv('AUTOCONTROL_ALLOWED_PATH_ROOTS', str(tmp_path))
    result = materialized(tmp_path)
    verify = profile_load._verified_result
    changed = Path(result['directory']) / 'scripts/demo.json'

    def replacement(*args, **kwargs):
        verified = verify(*args, **kwargs)
        changed.write_bytes(b'[]')
        return verified

    monkeypatch.setattr(profile_load, '_verified_result', replacement)
    with pytest.raises(ac.ConfigSyncError):
        ac.load_sync_profile(result['directory'], tmp_path / 'workspaces', expected_digest=result['manifest_digest'])
    assert changed.read_bytes() == b'[]'
    no_workspace(tmp_path)


@pytest.mark.parametrize('signal', [CancelledError(), KeyboardInterrupt(), SystemExit(2)],
                         ids=['cancel', 'interrupt', 'exit'])
def test_wrapped_io_interruptions_keep_the_original_signal_and_clean_staging(tmp_path, monkeypatch, signal):
    monkeypatch.setenv('AUTOCONTROL_ALLOWED_PATH_ROOTS', str(tmp_path))
    result = materialized(tmp_path)

    def interrupted(*_args, **_kwargs):
        raise OSError('interrupted native copy') from signal

    monkeypatch.setattr(profile_load, '_copy_stream', interrupted)
    with pytest.raises(type(signal)) as caught:
        ac.load_sync_profile(result['directory'], tmp_path / 'workspaces', expected_digest=result['manifest_digest'])
    assert caught.value is signal
    no_workspace(tmp_path)
