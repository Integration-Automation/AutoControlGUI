"""Modernization examples validate locally, retain configuration parity and document metadata."""
import json
import re
import runpy
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[3]
EXAMPLES = ('28_wayland_diagnostics', '29_config_sync', '30_mobile_devices',
            '31_healing_comparison', '32_codegen_from_log', '33_mcp_progressive')


@pytest.mark.parametrize('name', EXAMPLES)
def test_examples_compile_and_validate_without_device(name, monkeypatch, capsys):
    import socket
    import je_auto_control as ac
    path = ROOT / 'examples' / (name + '.py')
    assert path.exists()
    compile(path.read_text(encoding='utf-8'), str(path), 'exec')
    effects = []
    def forbidden(*args, **kwargs):
        effects.append((args, kwargs))
        raise AssertionError('validate attempted native or network work')
    monkeypatch.setattr(socket.socket, 'connect', forbidden)
    monkeypatch.setattr(ac.DeviceSession, 'adapter', forbidden)
    for operation in ('mobile_capture', 'mobile_gesture', 'mobile_type_text', 'click_mouse', 'press_keyboard_key', 'screenshot'):
        monkeypatch.setattr(ac, operation, forbidden)
    monkeypatch.setattr(sys, 'argv', [str(path), '--validate'])
    runpy.run_path(str(path), run_name='__main__')
    report = json.loads(capsys.readouterr().out)
    assert report['validated'] is True
    assert effects == []


def test_readme_configuration_parity():
    paths = ('README.md', 'README/README_zh-TW.md', 'README/README_zh-CN.md')
    keys = [set(re.findall(r'JE_AUTOCONTROL_[A-Z0-9_]+', (ROOT / path).read_text(encoding='utf-8')))
            for path in paths]
    assert keys[0] == keys[1] == keys[2]
    for name in EXAMPLES:
        assert all(name in (ROOT / path).read_text(encoding='utf-8') for path in paths)


def test_matrix_matches_capabilities():
    import je_auto_control as ac
    text = (ROOT / 'docs/CAPABILITY_MATRIX.md').read_text(encoding='utf-8')
    assert all(row['operation'] in text for row in ac.mobile_surface_matrix()['operations'])
    assert all(name in text for name in ('input', 'capture', 'restore_token'))
