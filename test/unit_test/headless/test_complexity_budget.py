"""No function in the package is over the documented complexity limit.

``CLAUDE.md`` sets cyclomatic complexity at 10 and names ``radon cc -nc`` as
the tool, but nothing ran it: it sat in the pre-commit list, "read by a human".
Measured on 2026-09-23 the whole package had exactly **one** function above the
limit, so the limit is cheap to hold — and a limit nobody measures is the one
that drifts.

``radon`` is the same tool the pre-commit list names, so the number here and
the number a developer sees are the same number.
"""
from pathlib import Path

import pytest

radon_complexity = pytest.importorskip(
    "radon.complexity", reason="pip install radon (see CLAUDE.md)")

_PACKAGE = Path(__file__).resolve().parents[3] / "je_auto_control"

#: ``CLAUDE.md`` § Size and complexity limits.
LIMIT = 10


def over_limit(source: str, limit: int = LIMIT):
    """``(name, complexity)`` for every block above ``limit``."""
    return [(block.fullname, block.complexity)
            for block in radon_complexity.cc_visit(source)
            if block.complexity > limit]


def test_no_function_in_the_package_is_over_the_limit():
    offenders = []
    for path in sorted(_PACKAGE.rglob("*.py")):
        if "__pycache__" in path.parts:
            continue
        for name, score in over_limit(path.read_text(encoding="utf-8")):
            offenders.append(
                f"{path.relative_to(_PACKAGE.parent).as_posix()}: {name} = {score}")
    assert not offenders, (
        f"cyclomatic complexity over {LIMIT} (split the function):\n"
        + "\n".join(offenders))


def test_the_measurement_sees_a_complex_function():
    """Positive control: an empty result above must mean clean, not blind."""
    branches = "\n".join(f"    if value == {index}:\n        return {index}"
                         for index in range(12))
    source = f"def busy(value):\n{branches}\n    return None\n"
    found = over_limit(source)
    assert [name for name, _ in found] == ["busy"]
    assert found[0][1] > LIMIT
    assert over_limit("def calm(value):\n    return value\n") == []
