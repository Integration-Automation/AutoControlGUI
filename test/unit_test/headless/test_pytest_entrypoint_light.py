"""The auto-loaded pytest plugin must not import the automation facade."""
import json
import os
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]


def _probe(source: str) -> dict:
    """Probe imports in a fresh interpreter, before pytest can preload them."""
    environment = dict(os.environ)
    environment["PYTHONPATH"] = str(ROOT)
    result = subprocess.run(
        [sys.executable, "-c", source], cwd=ROOT, env=environment,
        capture_output=True, text=True, timeout=30, check=False,
    )
    assert result.returncode == 0, result.stderr
    return json.loads(result.stdout)


def test_entrypoint_import_is_light():
    """Loading the automatic plugin leaves desktop backends and Qt unloaded."""
    result = _probe("""
import json
import sys
import je_auto_control_pytest
print(json.dumps({
    'facade': 'je_auto_control' in sys.modules,
    'qt': any(name.startswith('PySide6') for name in sys.modules),
    'plugin': hasattr(je_auto_control_pytest, 'pytest_configure'),
}))
""")
    assert result == {"facade": False, "qt": False, "plugin": True}


def test_legacy_plugin_exports_same_hooks():
    """Explicit legacy plugin users get the same fixtures and hook objects."""
    result = _probe("""
import json
import je_auto_control_pytest as standalone
from je_auto_control.utils.pytest_plugin import plugin as legacy
print(json.dumps({
    name: getattr(legacy, name) is getattr(standalone, name)
    for name in standalone.__all__
}))
""")
    assert result
    assert all(result.values())
