"""Portable manifest identity binds immutable file descriptors without claiming verified bytes."""
from copy import deepcopy
from dataclasses import FrozenInstanceError, replace
from hashlib import sha256
import importlib
import json

import pytest

from je_auto_control.utils.agent_runtime.errors import AgentTaskError
from je_auto_control.utils.config_sync.blob_models import CHUNK_BYTES
from je_auto_control.utils.config_sync.blob_store import SyncAssetStore
from je_auto_control.utils.config_sync.contract import ConfigSyncError


def manifest_type():
    module = importlib.import_module('je_auto_control.utils.agent_runtime.transfer_models')
    selected = getattr(module, 'TransferManifest', None)
    assert selected is not None, 'TransferManifest is not implemented'
    return selected


def manifest_value():
    return {'contract': 1, 'export_id': 'a' * 32, 'source_task': 'b' * 32,
            'source_snapshot': 'c' * 64, 'submission_digest': 'd' * 64,
            'files': [{'name': 'empty.bin', 'size': 0, 'sha256': sha256(b'').hexdigest(), 'chunks': []}],
            'expires': 4_000_000_000.0}


def test_manifest_round_trip_detaches_empty_file_and_hashes_exact_canonical_envelope():
    original = manifest_value()
    expected = deepcopy(original)
    manifest = manifest_type().from_dict(original)
    original['files'][0]['name'] = 'changed.bin'
    original['files'][0]['chunks'].append('f' * 64)

    assert manifest.to_dict() == expected
    assert isinstance(manifest.files, tuple)
    encoded = json.dumps(expected, sort_keys=True, separators=(',', ':'), allow_nan=False).encode('utf-8')
    assert manifest.digest == sha256(encoded).hexdigest()
    exported = manifest.to_dict()
    exported['files'][0]['chunks'].append('f' * 64)
    assert manifest.to_dict() == expected
    with pytest.raises(FrozenInstanceError):
        manifest.export_id = 'e' * 32
    with pytest.raises(FrozenInstanceError):
        manifest.files[0].name = 'another.bin'


@pytest.mark.parametrize(('field', 'value'), [
    ('contract', True), ('contract', 1.0), ('contract', '1'), ('contract', None), ('contract', 2),
    ('export_id', 'A' * 32), ('export_id', 'g' * 32), ('export_id', 'a' * 31), ('export_id', 1),
    ('source_task', 'b' * 31), ('source_task', True),
    ('source_snapshot', 'c' * 63), ('source_snapshot', 'C' * 64), ('source_snapshot', None),
    ('submission_digest', 'd' * 65), ('submission_digest', 'z' * 64),
    ('expires', True), ('expires', None), ('expires', '4000'), ('expires', float('nan')),
    ('expires', float('inf')), ('expires', float('-inf')), ('expires', 10 ** 400),
    ('files', None), ('files', []), ('files', tuple(manifest_value()['files'])),
    ('files', [False]), ('files', [None]), ('files', [1]), ('files', [{}]),
    ('principal', {'user_id': 'foreign'}), ('roots', ['D:/unrelated']), ('input_authorized', True),
])
def test_manifest_rejects_malformed_identity_deadline_shape_and_authority_fields(field, value):
    payload = manifest_value()
    payload[field] = value
    with pytest.raises(AgentTaskError):
        manifest_type().from_dict(payload)


@pytest.mark.parametrize('value', [None, [], True, {'contract': 1}])
def test_manifest_requires_the_exact_complete_wire_object(value):
    with pytest.raises(AgentTaskError):
        manifest_type().from_dict(value)


@pytest.mark.parametrize(('field', 'value'), [
    ('name', '../x'), ('name', '..\\x'), ('name', 'folder/x'), ('name', 'C:\\x'),
    ('name', '/absolute'), ('name', '//server/share'), ('name', 'NUL'), ('name', 'AUX.txt'),
    ('name', 'p:stream'), ('name', '*'), ('name', 'a.'), ('name', '.'), ('name', '..'),
    ('name', ''), ('name', 'nul\x00.bin'), ('name', '\n'), ('name', 1), ('name', None),
    ('size', True), ('size', 1.0), ('size', -1), ('size', 64 * 1024 * 1024 + 1),
    ('size', None), ('size', '0'), ('sha256', 'F' * 64), ('sha256', 'g' * 64),
    ('sha256', 'a' * 63), ('sha256', None), ('sha256', '0' * 64),
    ('chunks', ()), ('chunks', 'none'), ('chunks', None), ('chunks', [False]), ('chunks', ['f' * 64]),
    ('owner', {'user_id': 'foreign'}),
])
def test_manifest_rejects_nonportable_or_inconsistent_file_envelopes(field, value):
    payload = manifest_value()
    payload['files'][0][field] = value
    with pytest.raises(AgentTaskError):
        manifest_type().from_dict(payload)


@pytest.mark.parametrize('names', [
    ['same.bin', 'same.bin'], ['same.bin', 'SAME.bin'], ['e\u0301.bin', '\u00e9.bin'],
])
def test_manifest_rejects_output_names_that_collide_on_supported_filesystems(names):
    payload = manifest_value()
    payload['files'] = [{**payload['files'][0], 'name': name} for name in names]
    with pytest.raises(AgentTaskError):
        manifest_type().from_dict(payload)


def test_manifest_rejects_501_distinct_files_before_publication():
    payload = manifest_value()
    payload['files'] = [{**payload['files'][0], 'name': f'{number}.bin'} for number in range(501)]
    with pytest.raises(AgentTaskError):
        manifest_type().from_dict(payload)


def file_descriptor(name, size):
    return {'name': name, 'size': size, 'sha256': 'e' * 64,
            'chunks': ['f' * 64] * ((size + 256 * 1024 - 1) // (256 * 1024))}


def test_manifest_rejects_combined_file_bytes_above_64_mib():
    payload = manifest_value()
    payload['files'] = [file_descriptor('full.bin', 64 * 1024 * 1024), file_descriptor('extra.bin', 1)]
    with pytest.raises(AgentTaskError):
        manifest_type().from_dict(payload)


@pytest.mark.parametrize(('field', 'value'), [
    ('export_id', True), ('source_snapshot', 'z' * 64), ('files', []), ('files', (object(),)),
    ('expires', float('nan')), ('expires', True),
])
def test_manifest_constructor_enforces_the_same_value_bounds(field, value):
    current = manifest_type().from_dict(manifest_value())
    with pytest.raises(AgentTaskError):
        replace(current, **{field: value})


@pytest.mark.parametrize(('field', 'value'), [('name', '../escape'), ('blob', 'untyped')])
def test_file_constructor_requires_a_portable_name_and_a_real_blob_descriptor(field, value):
    current = manifest_type().from_dict(manifest_value()).files[0]
    with pytest.raises(AgentTaskError):
        replace(current, **{field: value})


@pytest.mark.parametrize('files', [
    [{**manifest_value()['files'][0], 'name': f'{number}.bin'} for number in range(500)],
    [file_descriptor('full.bin', 64 * 1024 * 1024)],
])
def test_structurally_valid_exact_file_and_byte_limits_round_trip(files):
    payload = manifest_value()
    payload['files'] = files
    assert manifest_type().from_dict(payload).to_dict() == payload


def test_manifest_digest_preserves_file_and_chunk_order_instead_of_attesting_bytes():
    payload = manifest_value()
    payload['files'] = [file_descriptor('pair.bin', 512 * 1024), manifest_value()['files'][0]]
    payload['files'][0]['chunks'] = ['1' * 64, '2' * 64]
    original = manifest_type().from_dict(payload)
    reordered = deepcopy(payload)
    reordered['files'].reverse()
    swapped = deepcopy(payload)
    swapped['files'][0]['chunks'].reverse()
    assert original.digest != manifest_type().from_dict(reordered).digest
    assert original.digest != manifest_type().from_dict(swapped).digest
    assert original.digest == manifest_type().from_dict(dict(reversed(list(payload.items())))).digest


def test_manifest_digest_keeps_integer_and_float_timestamps_distinct():
    value = manifest_value()
    first = manifest_type().from_dict(value)
    value['expires'] = int(value['expires'])
    second = manifest_type().from_dict(value)
    assert type(second.to_dict()['expires']) is int
    assert first.digest != second.digest


def test_swapped_chunk_proposal_cannot_publish_real_bytes_under_the_original_digest(tmp_path):
    bodies = (b'a' * CHUNK_BYTES, b'b' * CHUNK_BYTES)
    hashes = [sha256(body).hexdigest() for body in bodies]
    value = manifest_value()
    value['files'] = [{'name': 'pair.bin', 'size': 2 * CHUNK_BYTES,
                       'sha256': sha256(b''.join(bodies)).hexdigest(), 'chunks': hashes}]
    original = manifest_type().from_dict(value)
    value['files'][0]['chunks'] = list(reversed(hashes))
    swapped = manifest_type().from_dict(value)
    store = SyncAssetStore(tmp_path / 'owned-chunks.sqlite3')
    for digest, body in zip(hashes, bodies):
        store.put_chunk('source-owner', digest, body)

    with pytest.raises(ConfigSyncError, match='hash'):
        store.commit('source-owner', swapped.files[0].blob)
    assert not store.contains('source-owner', swapped.files[0].blob)
    assert store.commit('source-owner', original.files[0].blob)
    with store.open('source-owner', original.files[0].blob) as stream:
        assert stream.read() == b''.join(bodies)
