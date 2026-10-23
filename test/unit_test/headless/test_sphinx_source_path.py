"""Documentation builds must import the checkout containing conf.py, independently of cwd."""
from pathlib import Path
import runpy
import sys


def test_sphinx_source_path_is_the_current_checkout_from_an_unrelated_cwd(tmp_path, monkeypatch):
    repository = Path(__file__).resolve().parents[3]
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(sys, "path", list(sys.path))
    runpy.run_path(str(repository / "docs" / "source" / "conf.py"))
    assert Path(sys.path[0]).resolve() == repository
