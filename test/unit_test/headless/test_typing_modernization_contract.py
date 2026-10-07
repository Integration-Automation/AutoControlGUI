"""Guard strict modernization scope, zero exemptions and typed SDK adapter outputs."""
import ast
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]


def test_exemptions_remain_empty():
    lines = (ROOT / 'test/verify/typing_contract_exempt.txt').read_text().splitlines()
    assert {line.strip() for line in lines if line.strip() and not line.startswith('#')} == set()


def test_new_modules_have_complete_annotations():
    config = (ROOT / 'pyproject.toml').read_text(encoding='utf-8')
    assert 'disallow_untyped_defs = true' in config
    assert 'disallow_any_generics = true' in config
    manifest = ROOT / 'test/verify/typing_modernization_modules.txt'
    assert manifest.exists()
    expected = {line.strip() for line in manifest.read_text().splitlines() if line and not line.startswith('#')}
    strict = config.rsplit('[[tool.mypy.overrides]]', 1)[1]
    assert set(re.findall(r'"(je_auto_control[^" ]+)"', strict)) == expected
    missing = []
    for module in manifest.read_text().splitlines():
        if not module or module.startswith('#'):
            continue
        path = ROOT / (module.replace('.', '/') + '.py')
        if not path.exists():
            path = ROOT / module.replace('.', '/') / '__init__.py'
        tree = ast.parse(path.read_text(encoding='utf-8'))
        for node in ast.walk(tree):
            if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            args = [*node.args.posonlyargs, *node.args.args, *node.args.kwonlyargs]
            args += [arg for arg in (node.args.vararg, node.args.kwarg) if arg]
            if node.returns is None or any(arg.annotation is None for arg in args if arg.arg not in ('self', 'cls')):
                missing.append(f'{module}:{node.name}')
    assert missing == []


def test_adapter_is_only_sdk_any_boundary():
    for platform, adapter in [('android', 'UIAutomatorDevice'), ('ios', 'IOSDevice')]:
        tree = ast.parse((ROOT / 'je_auto_control' / platform / 'client.py').read_text(encoding='utf-8'))
        cls = next(node for node in tree.body if isinstance(node, ast.ClassDef) and node.name == adapter)
        handle = next(node for node in cls.body if isinstance(node, ast.FunctionDef) and node.name == 'handle')
        assert ast.unparse(handle.returns) in ('AndroidSDK', 'IOSSDK')
    owner = ast.parse((ROOT / 'je_auto_control/wrapper/device_context.py').read_text(encoding='utf-8'))
    annotations = [ast.unparse(node.returns) for node in ast.walk(owner)
                   if isinstance(node, ast.FunctionDef) and node.name == 'adapter']
    assert 'UIAutomatorDevice' in annotations and 'IOSDevice' in annotations
    workflow = (ROOT / '.github/workflows/quality.yml').read_text(encoding='utf-8')
    assert 'typing-extras:' in workflow
    assert 'typing_contract_verify.py --extras' in workflow
