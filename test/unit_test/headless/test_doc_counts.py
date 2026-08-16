"""The counts quoted in the docs must match the tree. No Qt.

CLAUDE.md requires `architecture_explore.md` and the three READMEs to be
updated with every change, and says every count in them is measured. Nothing
enforced it, and it drifted in practice: wiring `utils/url_canon` added three
commands and three MCP tools while every document kept quoting the old totals.
That was caught by hand afterwards, not by any check.

A mismatch here means one of two things, and the message says which:
the number moved and the docs were not updated, or the sentence holding the
number was reworded and this test's pattern needs to follow it.
"""
import pathlib
import re
from typing import Callable, List, Tuple

import pytest

ROOT = pathlib.Path(__file__).resolve().parents[3]


def _commands() -> int:
    from je_auto_control.utils.executor.action_executor import executor
    return len(executor.known_commands())


def _mcp_tools() -> int:
    from je_auto_control.utils.mcp_server.tools import build_default_tool_registry
    return len(build_default_tool_registry())


def _utils_subpackages() -> int:
    utils = ROOT / "je_auto_control" / "utils"
    return sum(1 for p in utils.iterdir()
               if p.is_dir() and (p / "__init__.py").exists())


def _examples() -> int:
    return len(list((ROOT / "examples").glob("*.py")))


# (doc, regex with one capture group, what it counts, how to measure it)
CITATIONS: List[Tuple[str, str, str, Callable[[], int]]] = [
    ("architecture_explore.md",
     r"`AC_\*` 動作指令數（`known_commands\(\)` 實測） \| (\d+) \|",
     "AC_* commands", _commands),
    ("architecture_explore.md",
     r"MCP 工具數（`build_default_tool_registry\(\)` 實測） \| (\d+) \|",
     "MCP tools", _mcp_tools),
    ("architecture_explore.md",
     r"### 5\.4 能力層 `utils/`（(\d+) 個子套件）",
     "utils/ subpackages", _utils_subpackages),
    ("README.md", r"(\d+) `AC_\*` commands", "AC_* commands", _commands),
    ("README.md", r"all (\d+) commands", "AC_* commands", _commands),
    ("README.md", r"(\d+) tools for", "MCP tools", _mcp_tools),
    ("README.md", r"(\d+) self-contained scripts", "examples", _examples),
    ("README/README_zh-CN.md", r"(\d+) 个 `AC_\*` 命令",
     "AC_* commands", _commands),
    ("README/README_zh-CN.md", r"全部 (\d+) 个命令", "AC_* commands", _commands),
    ("README/README_zh-CN.md", r"(\d+) 个工具", "MCP tools", _mcp_tools),
    ("README/README_zh-TW.md", r"(\d+) 個 `AC_\*` 指令",
     "AC_* commands", _commands),
    ("README/README_zh-TW.md", r"全部 (\d+) 個指令", "AC_* commands", _commands),
    ("README/README_zh-TW.md", r"(\d+) 個工具", "MCP tools", _mcp_tools),
    ("CLAUDE.md", r"(\d+) `utils/` subpackages",
     "utils/ subpackages", _utils_subpackages),
    ("CLAUDE.md", r"\((\d+) headless subpackages\)",
     "utils/ subpackages", _utils_subpackages),
    ("CLAUDE.md", r"partition all (\d+) subpackages",
     "utils/ subpackages", _utils_subpackages),
]


@pytest.mark.parametrize("doc,pattern,label,measure", CITATIONS,
                         ids=[f"{d}:{lbl}" for d, _p, lbl, _m in CITATIONS])
def test_quoted_count_matches_the_tree(doc, pattern, label, measure):
    text = (ROOT / doc).read_text(encoding="utf-8")
    found = re.findall(pattern, text)
    assert found, (
        f"{doc}: no longer states the {label} count in the expected form "
        f"({pattern!r}). If the wording changed on purpose, update this "
        f"test's pattern; the count itself must stay in the document."
    )
    actual = measure()
    for quoted in found:
        assert int(quoted) == actual, (
            f"{doc} says {quoted} {label}, the tree has {actual}. "
            f"Re-measure and update every document that quotes it "
            f"(architecture_explore.md, README.md and both translations)."
        )


def test_every_citation_target_exists():
    """A renamed doc must not silently switch this guard off."""
    for doc, _pattern, _label, _measure in CITATIONS:
        assert (ROOT / doc).is_file(), f"missing documentation file: {doc}"
