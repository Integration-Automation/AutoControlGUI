"""The Sphinx tree reads without a single warning.

Every warning Sphinx gives while *reading* -- a title underline shorter than
its title, inline markup that never closes because it touches a CJK character,
a malformed table, a duplicate label, a page no toctree reaches -- is a page
that renders wrong, usually in one language only. The tree had 181 of them;
this holds it at zero.

The ``dummy`` builder reads and cross-checks every page and writes nothing, so
it costs seconds where the HTML build costs minutes. The HTML build itself,
with the same ``-W``, is the ``docs`` job of ``quality.yml``.
"""
import os
import re
import subprocess
import sys
from pathlib import Path
from typing import List

import pytest

REPO_ROOT = Path(__file__).resolve().parents[3]
SOURCE = REPO_ROOT / "docs" / "source"
_ANSI = re.compile(r"\x1b\[[0-9;]*m")
_PROBLEM = re.compile(r"\b(WARNING|ERROR|CRITICAL|SEVERE)\b")


def _problems(output: str) -> List[str]:
    """The warning and error lines of a Sphinx run, colour codes removed."""
    return [line for line in _ANSI.sub("", output).splitlines() if _PROBLEM.search(line)]


def test_every_page_reads_without_a_warning(tmp_path):
    # The suite's own CI job does not install Sphinx; the `docs` job builds the HTML.
    pytest.importorskip("sphinx")
    pytest.importorskip("sphinx_rtd_theme")
    env = dict(os.environ, PYTHONPATH=str(REPO_ROOT), PYTHONIOENCODING="utf-8", NO_COLOR="1")
    done = subprocess.run(  # nosec B603  # nosemgrep  # reason: this interpreter, repository files, no shell
        [sys.executable, "-m", "sphinx", "-b", "dummy", "-E", "-W", "--keep-going",
         "-d", str(tmp_path / "doctrees"), str(SOURCE), str(tmp_path / "out")],
        cwd=REPO_ROOT, env=env, capture_output=True, text=True, encoding="utf-8",
        errors="replace", timeout=300, check=False)
    problems = _problems(done.stdout + done.stderr)
    assert problems == [], "\n".join(problems[:40])
    assert done.returncode == 0, (done.stdout + done.stderr)[-2000:]


def test_the_configuration_names_no_missing_directory():
    """``html_static_path`` / ``templates_path`` entries must exist (the HTML build warns otherwise)."""
    text = (SOURCE / "conf.py").read_text(encoding="utf-8")
    match = re.search(r"^html_static_path\s*=\s*\[(.*?)\]", text, flags=re.MULTILINE)
    names = re.findall(r"['\"]([^'\"]+)['\"]", match.group(1)) if match else []
    assert [name for name in names if not (SOURCE / name).is_dir()] == []


def test_the_docs_job_builds_html_with_warnings_as_errors():
    """CI runs the build this file only approximates; keep the flag that makes it a gate."""
    workflow = (REPO_ROOT / ".github" / "workflows" / "quality.yml").read_text(encoding="utf-8")
    assert re.search(r"^  docs:\n", workflow, flags=re.MULTILINE), "quality.yml has no `docs` job"
    assert re.search(r"sphinx -b html [^\n]*-W\b[^\n]*docs/source", workflow), (
        "the docs job no longer builds HTML with -W")
