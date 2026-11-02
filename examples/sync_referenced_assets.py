"""Synchronize a real script and selected template over loopback without executing received work."""
from hashlib import sha256
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import struct
import zlib

from examples.causal_peer_control import loopback_server
from je_auto_control import CausalConfigStore, SyncAssetStore, SyncReference, SyncWorkspace
from je_auto_control.utils.path_guard import PathPolicy


def configuration(root: Path, endpoint: str, *, sender: bool) -> dict[str, object]:
    """Select an exact native action file and bind one image argument to a private asset alias."""
    root.mkdir()
    source: dict[str, object] = {'records': {}}
    bindings: dict[str, object] = {}
    if sender:
        image = root / 'template.png'
        image.write_bytes(_template_png())
        actions = [['AC_locate_image_center', {'image': str(image)}]]
        (root / 'demo.json').write_text(json.dumps(actions), encoding='utf-8')
        source = {'path': str(root), 'paths': ['demo.json']}
        bindings = {'fields': {'demo.json': {'/actions/0/1/image': SyncReference('local', 'button').to_dict()}},
                    'local_values': {'button': str(image)}, 'assets': {'button': 'assets/template.png'}}
    return {'schema_version': 1, 'endpoint': endpoint, 'user_id': 'example',
            'outbox_path': str(root / 'outbox.sqlite3'), 'asset_cache_path': str(root / 'cache.sqlite3'),
            'profiles': [{'kind': 'scripts', 'state_path': str(root / 'adapter.sqlite3'),
                          'source': source, 'bindings': bindings}]}


def _template_png() -> bytes:
    pixels = b''.join(sha256(index.to_bytes(4, 'big')).digest() for index in range(512 * 512 * 3 // 32))
    rows = b''.join(b'\0' + pixels[index * 1536:(index + 1) * 1536] for index in range(512))
    header = struct.pack('!2I5B', 512, 512, 8, 2, 0, 0, 0)
    return (b'\x89PNG\r\n\x1a\n' + _png_chunk(b'IHDR', header)
            + _png_chunk(b'IDAT', zlib.compress(rows)) + _png_chunk(b'IEND', b''))


def _png_chunk(kind: bytes, body: bytes) -> bytes:
    return len(body).to_bytes(4, 'big') + kind + body + zlib.crc32(kind + body).to_bytes(4, 'big')


def main() -> None:
    """Run with temporary sources/server/cache and zero external, GUI, device or script execution calls."""
    with TemporaryDirectory(prefix='autocontrol-referenced-assets-') as temporary:
        root = Path(temporary)
        with loopback_server(CausalConfigStore(root / 'server.sqlite3'),
                              SyncAssetStore(root / 'server-assets.sqlite3')) as endpoint:
            policy = PathPolicy([root])
            left = configuration(root / 'desktop', endpoint, sender=True)
            right = configuration(root / 'laptop', endpoint, sender=False)
            sender = SyncWorkspace(left, path_policy=policy)
            captured = sender.capture()
            SyncWorkspace(left, path_policy=policy).synchronize()
            receiver = SyncWorkspace(right, path_policy=policy)
            result = receiver.synchronize()
            generation = receiver.materialize(root / 'profiles')
            original = (root / 'desktop/template.png').read_bytes()
            received = (generation.directory / 'assets/template.png').read_bytes()
            if original != received or result.pending or result.unresolved:
                raise RuntimeError('controlled referenced asset did not converge')
            print(json.dumps({'captured_offline': captured, 'files': generation.file_count,
                              'received_sha256': sha256(received).hexdigest(), 'bytes': len(received),
                              'script_executions': 0, 'active_workspace_changes': 0, 'external_calls': 0}))


if __name__ == '__main__':
    main()
