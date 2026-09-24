"""The 750-line limit and its exemption list, checked instead of remembered.

``CLAUDE.md`` says every file stays under 750 lines, that the only place a
standing exception may live is ``Progress.md``, and that the list is measured
rather than remembered — but nothing measured it. The list went stale twice in
2026-08 (every row had grown; the file quoting them said so only after someone
re-ran the count by hand), which is exactly the failure mode the rule was
written against.

So this reads the two lists in ``Progress.md`` — the ceiling table, whose
entries may shrink but never grow, and the flat-data-table paragraph — and
compares them with the tree:

* a file over the limit that is on neither list is a defect;
* a file on the ceiling table that grew past its recorded ceiling is a defect;
* a row for a file that is now under the limit is stale and should go.
"""
import re
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[3]
_PACKAGE = _REPO_ROOT / "je_auto_control"
_PROGRESS = _REPO_ROOT / "Progress.md"

LIMIT = 750

_CEILING_ROW = re.compile(r"^\|\s*`([^`]+\.py)`\s*\|\s*([\d,]+)\s*\|", re.MULTILINE)
_FLAT_SECTION = re.compile(r"\*\*本質豁免.*?。\n", re.DOTALL)
_BRACED = re.compile(r"^(.*)\{([^}]*)\}(.*)$")


def _line_count(path: Path) -> int:
    return len(path.read_text(encoding="utf-8").splitlines())


def ceiling_table(progress: str) -> dict:
    """``{package-relative path: recorded ceiling}`` from the exemption table."""
    return {path: int(count.replace(",", ""))
            for path, count in _CEILING_ROW.findall(progress)}


def flat_table_files(progress: str) -> set:
    """Package-relative paths named in the flat-data-table paragraph."""
    section = _FLAT_SECTION.search(progress)
    if section is None:
        return set()
    names = set()
    for quoted in re.findall(r"`([^`]+\.py)`", section.group(0)):
        braced = _BRACED.match(quoted)
        if braced is None:
            names.add(quoted)
            continue
        head, options, tail = braced.groups()
        names.update(f"{head}{option}{tail}" for option in options.split(","))
    return names


def _package_files() -> dict:
    return {path.relative_to(_PACKAGE).as_posix(): _line_count(path)
            for path in _PACKAGE.rglob("*.py")
            if "__pycache__" not in path.parts}


def test_every_file_over_the_limit_is_on_a_list():
    progress = _PROGRESS.read_text(encoding="utf-8")
    listed = set(ceiling_table(progress)) | flat_table_files(progress)
    # The table quotes paths under `je_auto_control/` both ways.
    listed |= {name.removeprefix("je_auto_control/") for name in listed}
    over = {name: count for name, count in _package_files().items()
            if count > LIMIT and name not in listed}
    assert not over, (
        f"over {LIMIT} lines and not in Progress.md's exemption list "
        "(split the file, or add a row saying why not):\n"
        + "\n".join(f"  {name}: {count}" for name, count in sorted(over.items())))


def test_no_exempted_file_grew_past_its_ceiling():
    progress = _PROGRESS.read_text(encoding="utf-8")
    measured = _package_files()
    grown = {}
    for name, ceiling in ceiling_table(progress).items():
        key = name.removeprefix("je_auto_control/")
        if key in measured and measured[key] > ceiling:
            grown[key] = (measured[key], ceiling)
    assert not grown, (
        "the exemption list allows shrinking only; these grew:\n"
        + "\n".join(f"  {name}: {now} > {ceiling}"
                    for name, (now, ceiling) in sorted(grown.items())))


def test_no_row_survives_the_file_going_under_the_limit():
    progress = _PROGRESS.read_text(encoding="utf-8")
    measured = _package_files()
    stale = {name: measured[name.removeprefix("je_auto_control/")]
             for name in ceiling_table(progress)
             if measured.get(name.removeprefix("je_auto_control/"), LIMIT + 1) <= LIMIT}
    assert not stale, (
        f"under {LIMIT} lines now — delete the row from Progress.md:\n"
        + "\n".join(f"  {name}: {count}" for name, count in sorted(stale.items())))


def test_the_lists_are_read_correctly():
    """Positive control: an empty result above must mean clean, not blind."""
    sample = (
        "| 檔案 | 行數 | 為何還沒拆 |\n"
        "| --- | ---: | --- |\n"
        "| `utils/a.py` | 1,448 | reason |\n"
        "| `gui/b.py` | 900 | reason |\n"
        "\n"
        "**本質豁免（依 `CLAUDE.md` 的「flat data tables」條款,不算既有豁免）**:\n"
        "`utils/c.py`（8,975,table）、\n"
        "`gui/lang/{one,two}.py`（1／2,catalogues）。\n")
    assert ceiling_table(sample) == {"utils/a.py": 1448, "gui/b.py": 900}
    assert flat_table_files(sample) == {"utils/c.py", "gui/lang/one.py",
                                        "gui/lang/two.py"}
