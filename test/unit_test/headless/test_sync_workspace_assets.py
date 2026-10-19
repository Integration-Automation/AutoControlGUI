"""Causal script versions carry content-addressed asset references and publish complete inert profiles only."""
from hashlib import sha256
import json
from pathlib import Path

import pytest

import je_auto_control as ac
from headless.test_sync_asset_http import transport as transport

OPTIONS = {'policy': {'max_attempts': 1, 'backoff': 0}}


def workspace(tmp_path, origin, *, content=None):
    root = tmp_path / origin
    root.mkdir()
    image = root / 'template.png'
    image.write_bytes(content or b'locally-selected-template')
    records = {'login.json': {'actions': [['AC_locate_image_center', {'image': str(image)}]]}} if content else {}
    config = {'schema_version': 1, 'endpoint': 'https://controlled.invalid', 'user_id': 'alice',
              'outbox_path': str(root / 'outbox.sqlite3'), 'asset_cache_path': str(root / 'assets.sqlite3'),
              'profiles': [{'kind': 'scripts', 'state_path': str(root / 'adapter.sqlite3'),
                            'source': {'records': records}, 'bindings': {
                                'fields': {'login.json': {'/actions/0/1/image':
                                                         ac.SyncReference('local', 'button').to_dict()}},
                                'local_values': {'button': str(image)}, 'assets': {'button': 'assets/template.png'}}}]}
    return ac.SyncWorkspace(config), config


def test_offline_capture_freezes_referenced_bytes_and_restart_sends_assets_before_causal_edits(tmp_path, transport,
                                                                                          monkeypatch):
    monkeypatch.setenv('AUTOCONTROL_ALLOWED_PATH_ROOTS', str(tmp_path))
    original = b'a' * (256 * 1024) + b'referenced-tail'
    sender, config = workspace(tmp_path, 'desktop', content=original)
    assert sender.capture() == 1 and not transport['calls']
    frozen = next(iter(sender.review('scripts').values())).value
    marker = frozen['actions'][0][1]['image']
    assert ac.SyncAssetReference.from_dict(marker).blob.sha256 == sha256(original).hexdigest()
    assert str(tmp_path) not in json.dumps(frozen)
    Path(config['profiles'][0]['bindings']['local_values']['button']).unlink()
    config['profiles'][0]['source'] = {'records': {'login.json': frozen}}
    config['profiles'][0]['bindings'] = {}
    result = ac.SyncWorkspace(config).synchronize(options=OPTIONS)
    assert result.pending == 0
    edits = [index for index, call in enumerate(transport['calls']) if call['method'] == 'PUT'
             and '/causal' in call['url'] and json.loads(call['body'])['bucket']['_actor']['mode'] == 'edit']
    commits = [index for index, call in enumerate(transport['calls']) if '/assets/blobs/' in call['url']]
    assert commits and edits and commits[0] < edits[0]
    receiver, _ = workspace(tmp_path, 'laptop')
    assert receiver.synchronize(options=OPTIONS).state == 'ready'
    generation = receiver.materialize(tmp_path / 'cache')
    assert (generation.directory / 'assets/template.png').read_bytes() == original
    script = json.loads((generation.directory / 'scripts/login.json').read_text(encoding='utf-8'))
    assert script[0][1]['image'] == 'assets/template.png'


def test_asset_only_changes_create_new_causal_versions(tmp_path, transport, monkeypatch):
    monkeypatch.setenv('AUTOCONTROL_ALLOWED_PATH_ROOTS', str(tmp_path))
    sender, config = workspace(tmp_path, 'desktop', content=b'first')
    sender.capture()
    before = next(iter(sender.review('scripts').values()))
    Path(config['profiles'][0]['bindings']['local_values']['button']).write_bytes(b'second')
    assert sender.capture() == 1
    after = next(iter(sender.review('scripts').values()))
    assert before.change_id != after.change_id and before.value != after.value
    assert sender.synchronize(options=OPTIONS).pending == 0
    receiver, _ = workspace(tmp_path, 'laptop')
    receiver.synchronize(options=OPTIONS)
    assert (receiver.materialize(tmp_path / 'cache').directory / 'assets/template.png').read_bytes() == b'second'


def test_incomplete_or_damaged_asset_download_cannot_publish_a_script_only_generation(tmp_path, transport, monkeypatch):
    monkeypatch.setenv('AUTOCONTROL_ALLOWED_PATH_ROOTS', str(tmp_path))
    sender, _ = workspace(tmp_path, 'desktop', content=b'asset')
    sender.synchronize(options=OPTIONS)
    receiver, config = workspace(tmp_path, 'laptop')
    def offline(call, _reply):
        if '/assets/chunks/' in call['url'] and call['method'] == 'GET':
            raise OSError('controlled download interruption')
    transport['after'] = offline
    result = receiver.synchronize(options=OPTIONS)
    assert result.state == 'offline' and result.unresolved
    with pytest.raises(ac.ConfigSyncError):
        receiver.materialize(tmp_path / 'cache')
    assert not list((tmp_path / 'cache').glob('generation-*'))
    transport['after'] = None
    restarted = ac.SyncWorkspace(config)
    assert restarted.synchronize(options=OPTIONS).state == 'ready'
    assert (restarted.materialize(tmp_path / 'cache').directory / 'assets/template.png').read_bytes() == b'asset'


def test_uncertain_definition_retry_sends_its_exact_put_before_asset_probe(tmp_path, transport, monkeypatch):
    monkeypatch.setenv('AUTOCONTROL_ALLOWED_PATH_ROOTS', str(tmp_path))
    sender, config = workspace(tmp_path, 'desktop', content=b'asset')
    lost = []
    def lose(call, _reply):
        if call['method'] == 'PUT' and '/causal' in call['url']:
            if json.loads(call['body'])['bucket']['_actor']['mode'] == 'edit' and not lost:
                lost.append(call['body'])
                raise OSError('controlled lost accepted definition reply')
    transport['after'] = lose
    assert sender.synchronize(options=OPTIONS).pending == 1
    transport['after'] = None
    transport['calls'].clear()
    assert ac.SyncWorkspace(config).synchronize(options=OPTIONS).pending == 0
    assert transport['calls'][0]['method'] == 'PUT' and '/causal' in transport['calls'][0]['url']
    assert transport['calls'][0]['body'] == lost[0]


def test_full_reset_does_not_replay_retired_source_asset_changes(tmp_path, transport, monkeypatch):
    monkeypatch.setenv('AUTOCONTROL_ALLOWED_PATH_ROOTS', str(tmp_path))
    sender, config = workspace(tmp_path, 'desktop', content=b'original')
    sender.synchronize(options=OPTIONS)
    Path(config['profiles'][0]['bindings']['local_values']['button']).write_bytes(b'retired-local-change')
    assert sender.capture() == 1
    sender.control(ac.SyncControlRequest('full_resync', discard_pending=True), options=OPTIONS)
    restarted = ac.SyncWorkspace(config)
    assert restarted.capture() == 0
    assert restarted.synchronize(options=OPTIONS).pending == 0
    generation = restarted.materialize(tmp_path / 'cache')
    assert (generation.directory / 'assets/template.png').read_bytes() == b'original'


def test_asset_capture_cancellation_keeps_chunks_without_recording_a_partial_source_edit(tmp_path, monkeypatch):
    from concurrent.futures import CancelledError
    from threading import Event
    monkeypatch.setenv('AUTOCONTROL_ALLOWED_PATH_ROOTS', str(tmp_path))
    _sender, config = workspace(tmp_path, 'desktop', content=b'a' * (256 * 1024 + 1))
    stopped = Event()
    original = ac.SyncAssetStore.put_chunk
    def accept_then_cancel(instance, *args):
        result = original(instance, *args)
        stopped.set()
        return result
    monkeypatch.setattr(ac.SyncAssetStore, 'put_chunk', accept_then_cancel)
    with pytest.raises(CancelledError):
        ac.SyncWorkspace(config, cancelled=stopped.is_set).capture()
    assert ac.SyncWorkspace(config).status()['outbox']['pending'] == 0
    assert not ac.SyncWorkspace(config).review('scripts')
    monkeypatch.setattr(ac.SyncAssetStore, 'put_chunk', original)
    assert ac.SyncWorkspace(config).capture() == 1


def test_wrapped_asset_source_io_cancellation_preserves_control_flow(tmp_path, monkeypatch):
    from concurrent.futures import CancelledError
    monkeypatch.setenv('AUTOCONTROL_ALLOWED_PATH_ROOTS', str(tmp_path))
    sender, _config = workspace(tmp_path, 'desktop', content=b'asset')
    original = Path.open
    def interrupted(path, *args, **kwargs):
        if path.name == 'template.png':
            raise OSError('controlled read interruption') from CancelledError()
        return original(path, *args, **kwargs)
    monkeypatch.setattr(Path, 'open', interrupted)
    with pytest.raises(CancelledError):
        sender.capture()


def test_assets_cannot_replace_a_private_command_secret_argument(tmp_path, transport, monkeypatch):
    monkeypatch.setenv('AUTOCONTROL_ALLOWED_PATH_ROOTS', str(tmp_path))
    _sender, config = workspace(tmp_path, 'desktop', content=b'do-not-send')
    profile = config['profiles'][0]
    profile['source']['records']['login.json']['actions'] = [['AC_write_secret', {'secret': 'private'}]]
    profile['bindings']['fields']['login.json'] = {'/actions/0/1/secret': ac.SyncReference('local', 'button').to_dict()}
    sender = ac.SyncWorkspace(config)
    with pytest.raises(ac.ConfigSyncError):
        sender.synchronize(options=OPTIONS)
    assert not transport['calls'] and sender.status()['outbox']['pending'] == 0


def test_script_and_image_trigger_share_complete_bytes_without_arming_received_work(tmp_path, transport, monkeypatch):
    monkeypatch.setenv('AUTOCONTROL_ALLOWED_PATH_ROOTS', str(tmp_path))
    _sender, config = workspace(tmp_path, 'desktop', content=b'image')
    script = config['profiles'][0]
    trigger = {'kind': 'triggers', 'state_path': script['state_path'], 'source': {'records': {'image': {
        'kind': 'image', 'script_path': 'scripts/login.json', 'repeat': False, 'cooldown_seconds': 1,
        'condition': {'image_path': script['bindings']['local_values']['button'], 'threshold': 0.8}}}},
        'bindings': dict(script['bindings'], fields={'image': {
            '/condition/image_path': ac.SyncReference('local', 'button').to_dict()}})}
    config['profiles'].append(trigger)
    ac.SyncWorkspace(config).synchronize(options=OPTIONS)
    _receiver, other = workspace(tmp_path, 'laptop')
    receiver_trigger = dict(trigger, state_path=other['profiles'][0]['state_path'], source={'records': {}})
    other['profiles'].append(receiver_trigger)
    receiver = ac.SyncWorkspace(other)
    assert receiver.synchronize(options=OPTIONS).state == 'ready'
    generation = receiver.materialize(tmp_path / 'cache')
    native = json.loads((generation.directory / 'triggers.json').read_text(encoding='utf-8'))
    assert native['triggers'][0]['enabled'] is False
    assert native['triggers'][0]['condition']['image_path'] == 'assets/template.png'
    assert generation.file_count == 5


def test_resolving_a_remote_reference_before_downloading_its_bytes_can_still_sync(tmp_path, transport, monkeypatch):
    monkeypatch.setenv('AUTOCONTROL_ALLOWED_PATH_ROOTS', str(tmp_path))
    sender, _ = workspace(tmp_path, 'desktop', content=b'asset')
    sender.synchronize(options=OPTIONS)
    receiver, _ = workspace(tmp_path, 'laptop')
    receiver.control('register', options=OPTIONS)
    heads = receiver.review('scripts')
    value = next(iter(heads.values())).value
    receiver.resolve('scripts', 'login.json', value, observed=heads)
    assert receiver.synchronize(options=OPTIONS).state == 'ready'
    assert (receiver.materialize(tmp_path / 'cache').directory / 'assets/template.png').read_bytes() == b'asset'


def test_factory_asset_paths_remain_bound_to_the_authorized_directory_after_chdir(tmp_path, monkeypatch):
    from je_auto_control.utils.path_guard import PathPolicy
    monkeypatch.setenv('AUTOCONTROL_ALLOWED_PATH_ROOTS', str(tmp_path))
    _sender, config = workspace(tmp_path, 'desktop', content=b'selected')
    root = tmp_path / 'desktop'
    profile = dict(config['profiles'][0], schema_version=1,
                   identity={'endpoint': config['endpoint'], 'user_id': 'alice', 'origin': 'desktop'})
    profile['bindings']['local_values']['button'] = 'template.png'
    monkeypatch.chdir(root)
    adapter = ac.adapter_from_profile(profile, path_policy=PathPolicy([root]))
    other = tmp_path / 'outside'
    other.mkdir()
    (other / 'template.png').write_bytes(b'outside-authorized-root')
    monkeypatch.chdir(other)
    heads = adapter.snapshot()
    value = next(iter(heads.values())).value['actions'][0][1]['image']
    assert ac.SyncAssetReference.from_dict(value).blob.sha256 == sha256(b'selected').hexdigest()


def test_portable_asset_destinations_cannot_hide_recognized_credentials(tmp_path, monkeypatch):
    monkeypatch.setenv('AUTOCONTROL_ALLOWED_PATH_ROOTS', str(tmp_path))
    _sender, config = workspace(tmp_path, 'desktop', content=b'asset')
    config['profiles'][0]['bindings']['assets']['button'] = 'assets/ghp_' + 'A' * 36 + '.png'
    sender = ac.SyncWorkspace(config)
    with pytest.raises(ac.ConfigSyncError):
        sender.capture()
    assert sender.status()['outbox']['pending'] == 0
