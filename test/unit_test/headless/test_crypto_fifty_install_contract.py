"""Secure dependency floors and typed failures without optional crypto libraries."""
import builtins
import pathlib
import re
import subprocess
import sys

import pytest
from packaging.requirements import Requirement
from packaging.version import Version

ROOT = pathlib.Path(__file__).resolve().parents[3]


def test_crypto_floor_is_fifty():
    text = (ROOT / 'pyproject.toml').read_text(encoding='utf-8')
    requirement = Requirement(re.search(r'"(cryptography[^"\n]+)"', text)[1])
    assert Version('49.0.0') not in requirement.specifier
    assert Version('50.0.0') in requirement.specifier
    assert requirement.marker.evaluate({'sys_platform': 'win32', 'platform_machine': 'ARM64'}) is False
    lock = (ROOT / 'uv.lock').read_text(encoding='utf-8')
    assert 'specifier = ">=50.0.0"' in lock


def test_arm64_import_has_no_crypto_requirement():
    probe = '''
import builtins, sys
original = builtins.__import__
def deny_crypto(name, *args, **kwargs):
    if name == 'cryptography' or name.startswith('cryptography.'):
        raise ImportError('simulated missing optional crypto')
    return original(name, *args, **kwargs)
builtins.__import__ = deny_crypto
import je_auto_control as ac
assert callable(ac.execute_action)
assert not any('PySide6' in name for name in sys.modules)
assert not any(name.startswith('cryptography') for name in sys.modules)
'''
    result = subprocess.run([sys.executable, '-c', probe], cwd=ROOT,
                            capture_output=True, text=True, timeout=30)
    assert result.returncode == 0, result.stderr


@pytest.mark.parametrize('feature', ['cipher', 'vault', 'signing'])
def test_missing_crypto_feature_is_typed(monkeypatch, tmp_path, feature):
    import je_auto_control as ac
    from je_auto_control.utils.secrets.secret_store import SecretManager
    original = builtins.__import__
    source = tmp_path / 'actions.json'
    source.write_text('[]')

    def deny_crypto(name, *args, **kwargs):
        if name == 'cryptography' or name.startswith('cryptography.'):
            raise ImportError('simulated missing optional crypto')
        return original(name, *args, **kwargs)

    monkeypatch.setattr(builtins, '__import__', deny_crypto)
    with pytest.raises(ac.CryptoDependencyError) as caught:
        if feature == 'cipher':
            ac.encrypt_action_file(source, key='fixture-passphrase')
        elif feature == 'vault':
            SecretManager(tmp_path / 'vault.json').initialize('fixture-passphrase')
        else:
            ac.create_signing_keypair(tmp_path / 'private.pem', tmp_path / 'public.pem')
    assert isinstance(caught.value, RuntimeError)
    assert 'pip install' in str(caught.value) and '>=50.0.0' in str(caught.value)
    assert not (tmp_path / 'actions.json.enc').exists()
    assert not (tmp_path / 'vault.json').exists()


@pytest.mark.parametrize('module', ['je_auto_control.utils.tls_acme.keys',
                                    'je_auto_control.utils.acme_v2.jws',
                                    'je_auto_control.utils.remote_desktop.jpeg_recorder_encrypted'])
def test_missing_crypto_module_is_typed(module):
    statement = (
        "import builtins\noriginal=builtins.__import__\n"
        "def deny(n,*a,**k):\n"
        " if n.startswith('cryptography'): raise ImportError('missing')\n"
        " return original(n,*a,**k)\n"
        "builtins.__import__=deny\n"
        "from je_auto_control import CryptoDependencyError\n"
        "try:\n __import__(" + repr(module) + ")\n"
        "except CryptoDependencyError as e:\n"
        " assert isinstance(e,ImportError)\n"
        " assert 'pip install' in str(e) and '>=50.0.0' in str(e)\n"
        "else:\n raise AssertionError('crypto unexpectedly available')\n")
    result = subprocess.run([sys.executable, '-c', statement], cwd=ROOT,
                            capture_output=True, text=True, timeout=30)
    assert result.returncode == 0, result.stderr
