"""Approved registry identity and repository links preserve package imports."""
from pathlib import Path
import re

import pytest

from je_auto_control.utils.mcp_registry import build_server_manifest

ROOT = Path(__file__).resolve().parents[3]
REPOSITORY = 'https://github.com/Integration-Automation/AutoControlGUI'


def test_registry_uses_approved_name():
    manifest = build_server_manifest()
    assert manifest['name'] == 'io.github.integration-automation/autocontrol'
    assert manifest['repository']['url'] == REPOSITORY
    assert manifest['packages'][0]['identifier'] == 'je_auto_control'


@pytest.mark.parametrize('name, package', [('pyproject.toml', 'je_auto_control'),
                                         ('dev.toml', 'je_auto_control_dev')])
def test_project_urls_use_current_repository(name, package):
    text = (ROOT / name).read_text(encoding='utf-8')
    assert re.search(r'^name = "' + package + '"', text, re.MULTILINE)
    assert f'Homepage = "{REPOSITORY}"' in text
    assert f'Code = "{REPOSITORY}"' in text


@pytest.mark.parametrize('name', ['README.md', 'README/README_zh-TW.md', 'README/README_zh-CN.md'])
def test_readme_links_use_current_repository(name):
    text = (ROOT / name).read_text(encoding='utf-8')
    assert f'git clone {REPOSITORY}.git' in text
    assert REPOSITORY in text
    assert 'Intergration-Automation-Testing/AutoControl' not in text
