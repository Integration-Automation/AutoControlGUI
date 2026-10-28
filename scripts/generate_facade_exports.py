"""Generate or check facade bindings without importing the application.

Run with --check in CI. --baseline accepts the pre-migration source audit
to compare original owners, aliases, optional groups and public order.
"""
from __future__ import annotations

import argparse
import ast
from dataclasses import dataclass
from hashlib import sha256
import json
from pathlib import Path
from typing import Sequence


ROOT = Path(__file__).resolve().parents[1]
PACKAGES = ("je_auto_control", "je_auto_control.utils.remote_desktop")
OPTIONAL = PACKAGES[1] + "._optional."
SPECIAL = {
    PACKAGES[0]: {"keyboard_keys_table", "start_autocontrol_gui"},
    PACKAGES[1]: {"registry", "is_webrtc_available"},
}


@dataclass(frozen=True)
class Binding:
    """Source spelling and runtime resolution of a concrete re-export."""

    owner: str
    attribute: str
    module: bool = False

    def render(self) -> str:
        """Return the generated binding constructor."""
        if self.module:
            return f"ModuleBinding({self.owner + '.' + self.attribute!r})"
        return f"AttributeBinding({self.owner!r}, {self.attribute!r})"


def source_path(module: str) -> Path:
    """Require an actual package or module source file."""
    path = ROOT.joinpath(*module.split("."))
    for candidate in (path.with_suffix(".py"), path / "__init__.py"):
        if candidate.is_file():
            return candidate
    raise ValueError(f"missing owner source: {module}")


def read_tree(module: str) -> ast.Module:
    """Read source only; this tool never imports a package to inspect it."""
    path = source_path(module)
    return ast.parse(path.read_text(encoding="utf-8"), filename=str(path))


def defines_attribute(module: str, name: str) -> bool:
    """A package's re-export takes precedence over a same-named child file."""
    pending = list(read_tree(module).body)
    while pending:
        node = pending.pop()
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            if node.name == name:
                return True
            continue
        if isinstance(node, (ast.ImportFrom, ast.Import)):
            for alias in node.names:
                if (alias.asname or alias.name.split(".")[0]) == name:
                    if isinstance(node, ast.ImportFrom) and node.module == module and alias.name == name:
                        continue
                    return True
        if isinstance(node, ast.Assign) and any(name in target_names(target) for target in node.targets):
            return True
        if isinstance(node, ast.AnnAssign) and node.value is not None and name in target_names(node.target):
            return True
        for field in ("body", "orelse", "finalbody"):
            pending.extend(getattr(node, field, []))
        if isinstance(node, ast.Try):
            pending.extend(statement for handler in node.handlers for statement in handler.body)
    return False


def child_module(module: str, name: str) -> bool:
    """Use exact source spelling even on case-insensitive filesystems."""
    parent = source_path(module)
    if parent.name != "__init__.py":
        return False
    return any((path.name == name + ".py" and path.is_file())
               or (path.name == name and (path / "__init__.py").is_file())
               for path in parent.parent.iterdir())


def target_names(target: ast.expr) -> list[str]:
    """Extract ordinary assignment names, including unpacked tuples."""
    if isinstance(target, ast.Name):
        return [target.id]
    if isinstance(target, (ast.Tuple, ast.List)):
        return [name for item in target.elts for name in target_names(item)]
    return []


def public_names(tree: ast.Module) -> list[str]:
    """Require one literal, duplicate-free ordered public list."""
    values = [node.value for node in tree.body if isinstance(node, ast.Assign)
              and any(target_names(target) == ["__all__"] for target in node.targets)]
    if len(values) != 1:
        raise ValueError("expected exactly one literal __all__")
    names = ast.literal_eval(values[0])
    if not isinstance(names, list) or not all(isinstance(name, str) for name in names):
        raise ValueError("__all__ must be a list of strings")
    if len(names) != len(set(names)):
        raise ValueError("duplicate public export")
    return names


def imported_bindings(nodes: Sequence[ast.stmt]) -> dict[str, Binding]:
    """Preserve the exact imported attribute behind every explicit alias."""
    result: dict[str, Binding] = {}
    for node in nodes:
        if not isinstance(node, ast.ImportFrom):
            continue
        if node.level or node.module is None:
            raise ValueError("export declarations must use absolute source modules")
        source_path(node.module)
        for alias in node.names:
            if alias.name == "*":
                raise ValueError("wildcard export declaration")
            name = alias.asname or alias.name
            if name in result:
                raise ValueError(f"duplicate export declaration: {name}")
            is_module = not defines_attribute(node.module, alias.name) and child_module(node.module, alias.name)
            if not is_module and not defines_attribute(node.module, alias.name):
                raise ValueError(f"missing source attribute: {node.module}.{alias.name}")
            result[name] = Binding(node.module, alias.name, is_module)
    return result


def declarations(tree: ast.Module) -> dict[str, Binding]:
    """Collect concrete type-checking imports, including platform branches."""
    nodes = [child for node in ast.walk(tree) if isinstance(node, ast.If)
             and isinstance(node.test, ast.Name) and node.test.id == "_TYPE_CHECKING"
             for child in node.body]
    bindings = imported_bindings(nodes)
    return bindings


def return_names(value: ast.expr | None) -> list[str]:
    """Only direct owner objects may leave an optional loader."""
    if value is None:
        raise ValueError("missing loader result")
    names = target_names(value)
    if not names:
        raise ValueError("optional loader must return original imported objects")
    return names


def optional_owners(module: str) -> dict[str, Binding]:
    """Verify each all-or-None outcome and trace it to the original owner."""
    tree = read_tree(module)
    loaders = [node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name == "_load"]
    if len(loaders) != 1:
        raise ValueError(f"{module}: expected one _load function")
    loader = loaders[0]
    if loader.returns is None or any(isinstance(node, ast.Name) and node.id == "Any"
                                     for node in ast.walk(loader.returns)):
        raise ValueError(f"{module}: optional result requires concrete types")
    body = loader.body
    if (body and isinstance(body[0], ast.Expr)
            and isinstance(body[0].value, ast.Constant) and isinstance(body[0].value.value, str)):
        body = body[1:]
    if len(body) != 2 or not isinstance(body[0], ast.Try) or not isinstance(body[1], ast.Return):
        raise ValueError(f"{module}: optional loader must be one import try and an object return")
    attempt = body[0]
    if attempt.orelse or attempt.finalbody or len(attempt.handlers) != 1:
        raise ValueError(f"{module}: unsupported optional failure policy")
    handler = attempt.handlers[0]
    if not isinstance(handler.type, ast.Name) or handler.type.id != "ImportError":
        raise ValueError(f"{module}: only ImportError may produce None")
    if len(handler.body) != 1 or not isinstance(handler.body[0], ast.Return):
        raise ValueError(f"{module}: failure must return the complete None outcome")
    if not all(isinstance(node, ast.ImportFrom) for node in attempt.body):
        raise ValueError(f"{module}: optional loader must import original owners directly")
    imports = imported_bindings(attempt.body)
    returned = return_names(body[1].value)
    failed = ast.literal_eval(handler.body[0].value)
    if failed != (None if len(returned) == 1 else (None,) * len(returned)):
        raise ValueError(f"{module}: failure changes the all-None group")
    assignments = [node for node in tree.body if isinstance(node, ast.Assign)
                   and isinstance(node.value, ast.Call) and isinstance(node.value.func, ast.Name)
                   and node.value.func.id == "_load"]
    if len(assignments) != 1 or len(assignments[0].targets) != 1:
        raise ValueError(f"{module}: expected one atomic outcome assignment")
    exported = target_names(assignments[0].targets[0])
    if len(exported) != len(returned) or set(returned) != set(imports):
        raise ValueError(f"{module}: incomplete optional owner/result mapping")
    return dict(zip(exported, (imports[name] for name in returned)))


def inspect_package(package: str) -> tuple[list[str], dict[str, Binding], dict[str, Binding]]:
    """Classify every public export and every immediate child-name collision."""
    tree = read_tree(package)
    names = public_names(tree)
    bindings = declarations(tree)
    if set(bindings) | SPECIAL[package] != set(names) or set(bindings) & SPECIAL[package]:
        raise ValueError(f"{package}: public declarations differ from __all__ or special exports")
    owners = dict(bindings)
    for name, binding in bindings.items():
        if binding.owner.startswith(OPTIONAL):
            group = optional_owners(binding.owner)
            if binding.attribute not in group:
                raise ValueError(f"{name}: missing optional outcome")
            owners[name] = group[binding.attribute]
            declared_group = {item.attribute for item in bindings.values() if item.owner == binding.owner}
            if declared_group != set(group):
                raise ValueError(f"{binding.owner}: facade does not declare the complete optional group")
    directory = source_path(package).parent
    children = {path.stem for path in directory.glob("*.py") if path.stem != "__init__"}
    children |= {path.name for path in directory.iterdir() if (path / "__init__.py").is_file()}
    collisions = set(names) & children
    expected = {"registry", "signaling_client"} if package == PACKAGES[1] else set()
    if collisions != expected:
        raise ValueError(f"{package}: unclassified child collisions: {collisions ^ expected}")
    if package == PACKAGES[1]:
        eager = imported_bindings([node for node in tree.body if isinstance(node, ast.ImportFrom)
                                  and node.module == package + ".registry"])
        if eager != {"registry": Binding(package + ".registry", "registry")}:
            raise ValueError("remote registry must retain its eager singleton binding")
        owners.update(eager)
        if bindings["signaling_client"] != Binding(package, "signaling_client", True):
            raise ValueError("signaling_client must remain the actual child module")
    return names, bindings, owners


def compare_baseline(path: Path, assignments_path: Path,
                     inspected: dict[str, tuple[list[str], dict[str, Binding], dict[str, Binding]]]) -> None:
    """Compare all original aliases and loader group membership, not just counts."""
    baseline = json.loads(path.read_text(encoding="utf-8"))["packages"]
    assignments = json.loads(assignments_path.read_text(encoding="utf-8"))["optional_assignments"]
    for package, (names, _bindings, owners) in inspected.items():
        original = baseline[package.replace(".", "/")]
        if names != original["ordered_exports"]:
            raise ValueError(f"{package}: ordered public contract changed")
        for name, expected in original["required_bindings"].items():
            actual = owners.get(name)
            if actual is None or (actual.owner, actual.attribute) != (expected["owner"], expected["attribute"]):
                raise ValueError(f"{package}.{name}: original owner or alias changed")
        current_groups = {binding.owner for binding in _bindings.values() if binding.owner.startswith(OPTIONAL)}
        current = {frozenset(optional_owners(group).values()) for group in current_groups}
        previous = set()
        for loader_name, loader in original["optional_loaders"].items():
            loader_tree = ast.parse(loader["source"])
            imported = imported_bindings([node for node in ast.walk(loader_tree)
                                          if isinstance(node, ast.ImportFrom)])
            previous.add(frozenset(imported.values()))
            returned = return_names(loader_tree.body[0].body[-1].value)
            targets = assignments[loader_name]
            if len(targets) != len(returned):
                raise ValueError(f"{loader_name}: incomplete original assignment contract")
            for public, local in zip(targets, returned):
                if owners.get(public) != imported[local]:
                    raise ValueError(f"{package}.{public}: original optional owner or alias changed")
        if current != previous:
            raise ValueError(f"{package}: original optional ownership or grouping changed")


def generated_source(names: list[str], bindings: dict[str, Binding]) -> str:
    """Render in public order so ordering drift is visible in --check."""
    constructors = "AttributeBinding, ExportBinding"
    if any(binding.module for binding in bindings.values()):
        constructors += ", ModuleBinding"
    order_digest = sha256(json.dumps(names).encode("utf-8")).hexdigest()
    lines = ['"""Generated by scripts/generate_facade_exports.py; edit concrete facade declarations."""',
             f"from je_auto_control._lazy_exports import {constructors}", "", "",
             f"PUBLIC_ORDER_SHA256 = {order_digest!r}", "", "EXPORTS: dict[str, ExportBinding] = {"]
    for name in names:
        if name in bindings:
            value = bindings[name].render()
            line = f"    {name!r}: {value},"
            if len(line) <= 120:
                lines.append(line)
            elif len(value) <= 111:
                lines.extend([f"    {name!r}:", f"        {value},"])
            else:
                binding = bindings[name]
                lines.extend([f"    {name!r}: AttributeBinding(",
                              f"        {binding.owner!r}, {binding.attribute!r},", "    ),"])
    lines += ["}", ""]
    return "\n".join(lines)


def main() -> int:
    """Fail rather than importing the application or accepting incomplete inputs."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true", help="fail if a generated mapping has drifted")
    parser.add_argument("--baseline", type=Path, help="also compare an original source contract JSON")
    parser.add_argument("--optional-assignments", type=Path, help="original optional assignment targets for --baseline")
    arguments = parser.parse_args()
    try:
        inspected = {package: inspect_package(package) for package in PACKAGES}
        if arguments.baseline is not None:
            if arguments.optional_assignments is None:
                raise ValueError("--baseline requires --optional-assignments to verify every optional alias")
            compare_baseline(arguments.baseline, arguments.optional_assignments, inspected)
        for package, (names, bindings, _owners) in inspected.items():
            path = source_path(package).with_name("_export_bindings.py")
            expected = generated_source(names, bindings)
            if arguments.check:
                if not path.is_file() or path.read_text(encoding="utf-8") != expected:
                    raise ValueError(f"{path.relative_to(ROOT)}: generated bindings differ; "
                                     f"rerun {Path(__file__).name}")
            else:
                path.write_text(expected, encoding="utf-8", newline="\n")
            print(f"{package}: {len(names)} ordered exports, {len(bindings)} lazy bindings checked")
    except (ValueError, KeyError, OSError, SyntaxError) as error:
        parser.exit(1, f"facade export contract: {error}\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
