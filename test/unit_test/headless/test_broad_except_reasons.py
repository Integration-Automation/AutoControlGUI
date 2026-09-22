"""Every broad ``except`` that swallows the exception says why, on its own line.

``CLAUDE.md`` asks for exactly this -- "suppressions need an inline
justification" -- and the workspace rules forbid swallowing an exception
silently. Neither was checked by anything: ``ruff`` runs with its default rule
set (no ``BLE``), pylint is not a CI job, and a grep for ``except Exception``
without ``reason`` turned up 24 handlers in September 2026, some with a bare
``# noqa`` and nothing else.

A handler is *broad* when it catches ``Exception`` or ``BaseException`` (alone
or in a tuple) or is a bare ``except:``. It *swallows* when nothing in its body
raises. Those need ``reason:`` in a comment on the ``except`` line; a handler
that cleans up and re-raises needs nothing.
"""
import ast
from pathlib import Path

_PACKAGE = Path(__file__).resolve().parents[3] / "je_auto_control"
_BROAD = {"Exception", "BaseException"}


def _is_broad(node) -> bool:
    if node is None:
        return True
    if isinstance(node, ast.Name):
        return node.id in _BROAD
    if isinstance(node, ast.Tuple):
        return any(_is_broad(element) for element in node.elts)
    return False


def _raises(handler: ast.ExceptHandler) -> bool:
    return any(isinstance(sub, ast.Raise)
               for statement in handler.body for sub in ast.walk(statement))


def unjustified_handlers(source: str):
    """Line numbers of broad, swallowing handlers without ``reason:``."""
    lines = source.splitlines()
    return [node.lineno for node in ast.walk(ast.parse(source))
            if isinstance(node, ast.ExceptHandler)
            and _is_broad(node.type) and not _raises(node)
            and "reason:" not in lines[node.lineno - 1]]


def test_every_swallowing_broad_except_in_the_package_says_why():
    offenders = []
    for path in sorted(_PACKAGE.rglob("*.py")):
        for line in unjustified_handlers(path.read_text(encoding="utf-8")):
            offenders.append(f"{path.relative_to(_PACKAGE.parent).as_posix()}:{line}")
    assert not offenders, (
        "broad except without '# reason:' on its line (narrow it, re-raise, "
        "or say why swallowing is right):\n" + "\n".join(offenders))


def test_the_scanner_sees_what_it_is_meant_to_see():
    """Positive control: an empty result above must mean clean, not blind."""
    source = (
        "try:\n    pass\nexcept Exception:\n    pass\n"
        "try:\n    pass\nexcept (OSError, BaseException):\n    pass\n"
        "try:\n    pass\nexcept:\n    pass\n"
    )
    assert unjustified_handlers(source) == [3, 7, 11]


def test_the_scanner_accepts_what_the_rule_allows():
    source = (
        "try:\n    pass\nexcept Exception:  # noqa: BLE001  # reason: x\n    pass\n"
        "try:\n    pass\nexcept BaseException:\n    cleanup()\n    raise\n"
        "try:\n    pass\nexcept OSError:\n    pass\n"
    )
    assert unjustified_handlers(source) == []
