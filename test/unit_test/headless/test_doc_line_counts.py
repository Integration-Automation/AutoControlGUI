"""Every line count in `architecture_explore.md` is measured, not remembered.

`CLAUDE.md` requires the map's figures to be re-measured rather than adjusted
by hand. The command / MCP-tool / subpackage / example counts have had a gate
in `test_doc_counts.py`; the *line* counts had none, and drifted two ways at
once. Most table rows counted a phantom trailing line — `len(text.split("\\n"))`
reports one more line than a file that ends in a newline actually has, and one
more *per file* for a package — while the §1 totals and the §8 appendix used
the real count. The same subsystem was therefore quoted at two different sizes
in one document, and roughly fifty rows were additionally just stale.

This module measures the tree and compares. `len(text.splitlines())` is the
convention it enforces everywhere: it is what `wc -l` reports, what the §8
appendix already used, and what `CLAUDE.md`'s own over-750-lines snippet
counts.

Run it directly to rewrite every figure in place rather than hand-editing:

    python test/unit_test/headless/test_doc_line_counts.py --fix
"""
from __future__ import annotations

import pathlib
import re
import sys
from typing import Dict, List, Optional, Tuple

ROOT = pathlib.Path(__file__).resolve().parents[3]
PACKAGE = ROOT / "je_auto_control"
DOC = ROOT / "architecture_explore.md"

FIX_COMMAND = "python test/unit_test/headless/test_doc_line_counts.py --fix"

# The scan scope quoted in the document header, for the §1 totals.
SCAN_SCOPE = ("je_auto_control", "autocontrol-lsp", "autocontrol_driver",
              "AutoControl", "exe", "benchmarks")

# Only tables whose header names 行數 hold line counts; §1's 指標／數值 table
# holds subpackage and command counts that must not be touched.
_LINE_TABLE_HEADERS = ("| 模組 | 行數 | 職責 |", "| 檔案 | 行數 | 職責 |")
_SIZE_TABLE_HEADER = "| 層／子系統 | 檔案數 | 行數 |"

_ROW = re.compile(r"^\|\s*`([^`]+)`")
_ONE_NUMBER = re.compile(r"^(\|[^|]*\|\s*)([\d,]+)(\s*\|)")
_TWO_NUMBERS = re.compile(r"^(\|[^|]*\|\s*)([\d,]+)(\s*\|\s*)([\d,]+)(\s*\|)")
_SUBSECTION = re.compile(r"^####\s")
_PATH_TICK = re.compile(r"`([^`]+/)`")
_PAREN = re.compile(r"（[^（）]*）")
_COUNT_OF = re.compile(r"(\d[\d,]*)(\s*(?:檔|行))")
_BLOCKQUOTE = re.compile(r"^> (\d[\d,]*) 個套件、約 (\d[\d,]*) 行。")
_METRIC_TOTAL_LINES = re.compile(r"^(\| 程式碼總行數 \| )([\d,]+)( \|)")
_METRIC_TOTAL_FILES = re.compile(r"^(\| Python 模組總數（含周邊子專案） \| )([\d,]+)( \|)")

# §8 rows that are not a plain path measurement.
_TOP_LEVEL_ROW = "je_auto_control/"           # 頂層 3 檔 — not recursive
_REMAINDER = "其餘模組"
_GRAND_TOTAL = "**總計**"


def _lines(path: pathlib.Path) -> int:
    return len(path.read_text(encoding="utf-8", errors="ignore").splitlines())


def _py_files(directory: pathlib.Path) -> List[pathlib.Path]:
    return [p for p in sorted(directory.rglob("*.py"))
            if "__pycache__" not in p.parts]


def _measure(target: pathlib.Path, *, recursive: bool = True) -> Tuple[int, int]:
    """``(files, lines)`` for a directory tree or a single file."""
    if target.is_file():
        return 1, _lines(target)
    files = _py_files(target) if recursive else sorted(target.glob("*.py"))
    return len(files), sum(_lines(p) for p in files)


def _resolve(name: str, context: Optional[str]) -> Optional[pathlib.Path]:
    """Find what a backticked name in the document refers to, or ``None``.

    Names are written relative to ``je_auto_control/`` in most tables, relative
    to the repo root in a few (``autocontrol-lsp/``), and as a bare file name
    in the §5.4.17 file tables — where the enclosing ``#### `utils/x/``` header
    supplies the package.
    """
    candidates = [PACKAGE / name, ROOT / name]
    if context and "/" not in name:
        candidates.insert(0, PACKAGE / context / name)
    for candidate in candidates:
        if candidate.is_file() or candidate.is_dir():
            return candidate
    return None


def _replace_numbers(line: str, values: Tuple[int, ...]) -> str:
    """Rewrite the one or two numeric cells of a table row."""
    if len(values) == 2:
        return _TWO_NUMBERS.sub(
            lambda m: f"{m.group(1)}{values[0]:,}{m.group(3)}{values[1]:,}{m.group(5)}",
            line, count=1)
    return _ONE_NUMBER.sub(
        lambda m: f"{m.group(1)}{values[0]:,}{m.group(3)}", line, count=1)


def _header_group_package(line: str, group: str) -> Optional[str]:
    """The package a ``（…）`` group on a heading describes, if any.

    The path is written either inside the group (``（`windows/`，23 檔…）``) or
    immediately before it (`` `utils/usb/`（4,238 行） ``).
    """
    inside = _PATH_TICK.search(group)
    if inside:
        return inside.group(1)
    outside = _PATH_TICK.findall(line.split(group)[0])
    return outside[-1] if outside else None


def _rewrite_header(line: str) -> str:
    """Rewrite the ``（… 檔／… 行）`` figures carried by a `####` heading."""
    result = line
    for group in _PAREN.findall(line):
        name = _header_group_package(result, group)
        target = _resolve(name, None) if name else None
        if target is None or not target.is_dir():
            continue
        files, total = _measure(target)
        result = result.replace(group, _fill_counts(group, files, total), 1)
    return result


def _fill_counts(text: str, files: int, lines: int) -> str:
    """Replace every ``N 檔`` with ``files`` and every ``N 行`` with ``lines``."""
    def _sub(match: "re.Match[str]") -> str:
        unit = match.group(2)
        return f"{files if '檔' in unit else lines:,}{unit}"
    return _COUNT_OF.sub(_sub, text)


def _row_name(line: str) -> Optional[str]:
    """The first cell of a table row, if it names something measurable."""
    match = _ROW.match(line)
    if match:
        return match.group(1)
    if _REMAINDER in line or _GRAND_TOTAL in line:
        return line.split("|")[1].strip()
    return None


def _table_rows(doc_lines: List[str]) -> Dict[int, Tuple[str, Optional[str]]]:
    """Map each measurable table row's index to ``(name, package context)``.

    Only tables headed 行數 are collected. §1's 指標／數值 table holds
    subpackage and command counts, which belong to ``test_doc_counts.py`` and
    must not be overwritten with a line count.
    """
    rows: Dict[int, Tuple[str, Optional[str]]] = {}
    context: Optional[str] = None
    header: Optional[str] = None
    for index, line in enumerate(doc_lines):
        if _SUBSECTION.match(line):
            paths = _PATH_TICK.findall(line)
            context = paths[0].rstrip("/") if paths else None
        if not line.startswith("|"):
            header = None
            continue
        stripped = line.rstrip()
        if stripped in _LINE_TABLE_HEADERS or stripped == _SIZE_TABLE_HEADER:
            header = stripped
            continue
        name = _row_name(line) if header is not None else None
        if name is not None:
            rows[index] = (name, context)
    return rows


def _section_totals(doc_lines: List[str], start: int) -> Optional[Tuple[int, int]]:
    """``(packages, lines)`` of the theme table that follows a blockquote."""
    index = start
    while index < len(doc_lines) and doc_lines[index].rstrip() not in _LINE_TABLE_HEADERS:
        if doc_lines[index].startswith("### "):
            return None
        index += 1
    if index >= len(doc_lines):
        return None
    packages = total = 0
    for line in doc_lines[index + 2:]:
        if not line.startswith("|"):
            break
        match = _ROW.match(line)
        if not match:
            continue
        target = _resolve(match.group(1), None)
        if target is None:
            continue
        packages += 1
        total += _measure(target)[1]
    return packages, total


def _scope_totals() -> Tuple[int, int]:
    files = total = 0
    for name in SCAN_SCOPE:
        directory = ROOT / name
        if not directory.is_dir():
            continue
        count, lines = _measure(directory)
        files += count
        total += lines
    return files, total


def _rewrite_table_rows(doc_lines: List[str]) -> Dict[str, object]:
    """Rewrite every measurable row; report what §8's derived rows need."""
    named_files = named_lines = 0
    derived: Dict[str, object] = {"remainder": None, "total": None}
    for index, (name, context) in _table_rows(doc_lines).items():
        line = doc_lines[index]
        if name.startswith(_REMAINDER):
            derived["remainder"] = index
            continue
        if name == _GRAND_TOTAL:
            derived["total"] = index
            continue
        two_columns = _TWO_NUMBERS.match(line) is not None
        target = _resolve(name, context)
        if target is None:
            continue
        files, total = _measure(
            target, recursive=not (two_columns and name == _TOP_LEVEL_ROW))
        if two_columns:
            named_files += files
            named_lines += total
        doc_lines[index] = _replace_numbers(
            line, (files, total) if two_columns else (total,))
    derived["named"] = (named_files, named_lines)
    return derived


def _rewrite_appendix_totals(doc_lines: List[str],
                             derived: Dict[str, object]) -> None:
    """Fill in §8's remainder and grand-total rows.

    Neither is measured on its own: the remainder is whatever the named rows
    did not account for, and the total is the appendix's whole scope. Deriving
    them is what makes the column actually add up, which it did not before.
    """
    files, lines = _measure(PACKAGE)
    lsp_files, lsp_lines = _measure(ROOT / "autocontrol-lsp")
    files, lines = files + lsp_files, lines + lsp_lines
    named_files, named_lines = derived["named"]  # type: ignore[misc]
    remainder = derived["remainder"]
    if remainder is not None:
        doc_lines[remainder] = _replace_numbers(
            doc_lines[remainder], (files - named_files, lines - named_lines))
    total = derived["total"]
    if total is not None:
        doc_lines[total] = re.sub(
            r"\*\*([\d,]+)\*\* \| \*\*([\d,]+)\*\*",
            f"**{files:,}** | **{lines:,}**", doc_lines[total], count=1)


def _rewrite_headings(doc_lines: List[str]) -> None:
    """Rewrite `####` headings and the ``> N 個套件、約 L 行。`` summaries."""
    for index, line in enumerate(doc_lines):
        if _SUBSECTION.match(line):
            doc_lines[index] = _rewrite_header(line)
        elif _BLOCKQUOTE.match(line):
            totals = _section_totals(doc_lines, index)
            if totals is not None:
                doc_lines[index] = f"> {totals[0]:,} 個套件、約 {totals[1]:,} 行。"


def _rewrite_scope_metrics(doc_lines: List[str]) -> None:
    """Rewrite §1's module and line totals over the documented scan scope."""
    files, lines = _scope_totals()
    for index, line in enumerate(doc_lines):
        line = _METRIC_TOTAL_LINES.sub(
            lambda m: f"{m.group(1)}{lines:,}{m.group(3)}", line)
        doc_lines[index] = _METRIC_TOTAL_FILES.sub(
            lambda m: f"{m.group(1)}{files:,}{m.group(3)}", line)


def rewrite(text: str) -> str:
    """Return ``text`` with every measurable figure replaced by a measurement."""
    doc_lines = text.split("\n")
    _rewrite_appendix_totals(doc_lines, _rewrite_table_rows(doc_lines))
    _rewrite_headings(doc_lines)
    _rewrite_scope_metrics(doc_lines)
    return "\n".join(doc_lines)


def mismatches() -> List[str]:
    """One line per figure that does not match the tree.

    Only the figures are reported, never the surrounding prose: the document is
    Chinese and a console on a cp950 code page cannot print it.
    """
    original = DOC.read_text(encoding="utf-8")
    fixed = rewrite(original)
    if original == fixed:
        return []
    found = []
    for number, (before, after) in enumerate(
            zip(original.split("\n"), fixed.split("\n")), 1):
        if before == after:
            continue
        was = " / ".join(re.findall(r"[\d,]{2,}", before)) or "?"
        now = " / ".join(re.findall(r"[\d,]{2,}", after)) or "?"
        found.append(f"line {number}: {was} -> {now}")
    return found


def test_every_quoted_line_count_matches_the_tree():
    """`architecture_explore.md` quotes measurements, so they have to measure."""
    found = mismatches()
    preview = "\n".join(found[:20])
    more = f"\n… and {len(found) - 20} more" if len(found) > 20 else ""
    assert not found, (
        f"{len(found)} line-count figures in architecture_explore.md no longer "
        f"match the tree. CLAUDE.md says to re-measure rather than adjust by "
        f"hand:\n\n    {FIX_COMMAND}\n\n{preview}{more}"
    )


def test_the_rewriter_is_idempotent():
    """A second pass must be a no-op, or --fix would churn the document."""
    once = rewrite(DOC.read_text(encoding="utf-8"))
    assert rewrite(once) == once


def _main(argv: List[str]) -> int:
    if "--fix" not in argv:
        found = mismatches()
        for entry in found:
            print(entry)
        print(f"{len(found)} figures out of date; rerun with --fix"
              if found else "every figure matches the tree")
        return 1 if found else 0
    original = DOC.read_text(encoding="utf-8")
    fixed = rewrite(original)
    if original == fixed:
        print("every figure already matches the tree")
        return 0
    DOC.write_text(fixed, encoding="utf-8")
    changed = sum(1 for a, b in zip(original.split("\n"), fixed.split("\n")) if a != b)
    print(f"rewrote {changed} lines in {DOC.name}")
    return 0


if __name__ == "__main__":
    sys.exit(_main(sys.argv[1:]))
