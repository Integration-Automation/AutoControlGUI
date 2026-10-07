"""Protect native source verification from empty or ineffective evidence."""
import importlib.util
from pathlib import Path
import re

import pytest


ROOT = Path(__file__).resolve().parents[3]


def _verifier():
    path = ROOT / 'docker/physical_source_verify.py'
    assert path.is_file(), 'the kernel source-exclusion verifier must ship with both input images'
    spec = importlib.util.spec_from_file_location('physical_source_verify', path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_open_guard_rejects_selected_device_but_allows_unrelated_reads():
    verifier = _verifier()
    guard = verifier.deny_selected_open({'/dev/input/event7'})
    guard('open', ('/etc/os-release', 'r', 0))
    guard('open', (4, 'r', 0))
    guard('other-event', ('/dev/input/event7',))
    with pytest.raises(AssertionError, match='before opening'):
        guard('open', (b'/dev/input/event7', None, 0))


def test_native_verifier_refuses_missing_virtual_sources(monkeypatch):
    verifier = _verifier()
    monkeypatch.setattr(verifier, 'source_paths', lambda: [])
    monkeypatch.setattr(verifier, 'package_identity', lambda: 'installed-wheel')
    with pytest.raises(AssertionError, match='one to sixteen'):
        verifier.verify_virtual_sources()


@pytest.mark.parametrize('image', ['seat', 'ydotool', 'portal', 'wayland', ''])
def test_input_images_ship_verifier_and_standalone_pytest_entrypoint(image):
    filename = f'Dockerfile.{image}' if image else 'Dockerfile'
    contents = (ROOT / 'docker' / filename).read_text(encoding='utf-8')
    if image in ('seat', 'ydotool'):
        assert 'COPY docker/physical_source_verify.py /opt/verify/physical_source_verify.py' in contents
    assert 'COPY pyproject.toml README.md je_auto_control_pytest.py ./' in contents


def test_native_input_jobs_preserve_failure_output_and_have_manual_scope():
    contents = (ROOT / '.github/workflows/docker.yml').read_text(encoding='utf-8')
    assert 'workflow_dispatch:' in contents
    assert 'd3-native' in contents
    for kind in ('seat', 'ydotool'):
        job = re.split(r'\n  [a-z][a-z0-9-]+:', contents.split(f'  {kind}-verification:', 1)[1])[0]
        assert f'tee {kind}-verification.log' in job
        assert 'if: always()' in job
        assert 'retention-days: 14' in job
        assert 'set -o pipefail' in job
