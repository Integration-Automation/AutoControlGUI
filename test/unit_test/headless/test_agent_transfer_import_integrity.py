"""Late destination mutation must not become an intact import receipt or overwrite user changes."""
from hashlib import sha256

import pytest

from headless.test_agent_transfer_import import import_hosts
from headless.test_agent_transfer_import_lifecycle import operation, review, wait_import
from je_auto_control.utils.agent_runtime import transfer_import


def change_output(directory, body, fault):
    output = directory / 'report.txt'
    assert output.read_bytes() == body
    if fault == 'same-size-bytes':
        output.write_bytes(b'x' * len(body))
    elif fault == 'unexpected-entry':
        (directory / 'unexpected.txt').write_bytes(b'owned extra output')
    elif fault == 'missing-file':
        output.unlink()


def assert_preserved(directory, body, fault):
    if fault == 'missing-file':
        assert list(directory.iterdir()) == []
        return
    expected = b'x' * len(body) if fault == 'same-size-bytes' else body
    assert (directory / 'report.txt').read_bytes() == expected
    if fault == 'unexpected-entry':
        assert (directory / 'unexpected.txt').read_bytes() == b'owned extra output'


@pytest.mark.parametrize('phase', ['after-publication', 'after-source-reply'])
@pytest.mark.parametrize('fault', ['none', 'same-size-bytes', 'unexpected-entry', 'missing-file'])
def test_late_import_mutation_requires_review_without_republishing(tmp_path, monkeypatch, phase, fault):
    with import_hosts(tmp_path, monkeypatch) as (host, server, exported, body, token, root, _actor):
        original_publish = transfer_import.publish_import
        original_manifest = transfer_import.TransferImporter._manifest
        publications, changed = [], []

        def mutate():
            if publications and not changed:
                change_output(publications[0], body, fault)
                changed.append(True)

        def published(*args):
            result = original_publish(*args)
            assert result.directory.resolve().is_relative_to(tmp_path.resolve())
            publications.append(result.directory)
            if phase == 'after-publication':
                mutate()
            return result

        def source_reply(importer, *args):
            result = original_manifest(importer, *args)
            if phase == 'after-source-reply':
                mutate()
            return result

        monkeypatch.setattr(transfer_import, 'publish_import', published)
        monkeypatch.setattr(transfer_import.TransferImporter, '_manifest', source_reply)
        status, accepted = operation(server, token, 'create_import', review(server, exported, token, root))
        assert status == 200, accepted
        current = wait_import(server, token, accepted['import']['import_id'])
        assert len(publications) == 1 and changed == [True]
        if fault == 'none':
            assert current['state'] == 'published', current
            assert sha256((publications[0] / 'report.txt').read_bytes()).hexdigest() == (
                exported['manifest']['files'][0]['sha256'])
        else:
            assert current['state'] == 'requires_review', current
            assert current['files_directory'] is None
        assert_preserved(publications[0], body, fault)
        assert host.runtime.list() == []
