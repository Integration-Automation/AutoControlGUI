"""Verify and atomically publish a complete local asset generation using temporary directories only."""
import json
from pathlib import Path
from tempfile import TemporaryDirectory

from je_auto_control import DirectoryAssetTransport, build_asset_manifest, sync_assets


def main() -> None:
    """Round-trip a script and referenced template as inert files with no device or network calls."""
    with TemporaryDirectory(prefix='autocontrol-assets-') as temporary:
        root = Path(temporary)
        source = root / 'source'
        source.mkdir()
        (source / 'template.bin').write_bytes(b'controlled-template-bytes')
        actions = [['AC_locate', {'template': 'template.bin'}]]
        (source / 'script.json').write_text(json.dumps(actions), encoding='utf-8')
        manifest = build_asset_manifest(source, ['script.json', 'template.bin'])
        transport = DirectoryAssetTransport(source, root / 'cache')
        result = sync_assets(manifest, transport)
        repeated = sync_assets(manifest, transport)
        print(json.dumps({'files': result.file_count, 'bytes': result.byte_count,
                          'manifest_digest': result.manifest_digest, 'reused': repeated.reused,
                          'script_executions': 0, 'network_calls': 0}))


if __name__ == '__main__':
    main()
