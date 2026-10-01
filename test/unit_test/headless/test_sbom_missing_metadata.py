"""The SBOM skips a distribution with no metadata instead of failing or inventing one.

A directory left by an interrupted uninstall is a distribution without a
METADATA file. Python 3.15 raises ``MetadataNotFound`` (a
``FileNotFoundError``) when its metadata is read, which ended the whole SBOM;
3.14 returns empty metadata whose missing keys are deprecated, and the SBOM
listed it as ``unknown`` at version ``0``. Both shapes are simulated here.
"""
import warnings
from importlib import metadata

from je_auto_control.utils.sbom import sbom


class _Dist(metadata.Distribution):
    def __init__(self, text):
        self._text = text

    def read_text(self, filename):
        return self._text if filename == "METADATA" else None

    def locate_file(self, path):
        return path


class _Python315Leftover(_Dist):
    @property
    def metadata(self):
        raise FileNotFoundError("No package metadata was found.")


def _dists():
    return [_Dist("Name: good\nVersion: 1.0\n"), _Python315Leftover(None), _Dist(None)]


def test_every_installed_distribution_without_metadata_is_skipped(monkeypatch):
    monkeypatch.setattr(sbom.metadata, "distributions", _dists)
    with warnings.catch_warnings():
        warnings.simplefilter("error")
        components = sbom.build_sbom(None)["components"]
    assert [(c["name"], c["version"]) for c in components] == [("good", "1.0")]


def test_a_dependency_without_metadata_is_skipped(monkeypatch):
    by_name = {"root": _Dist("Name: root\nVersion: 2.0\nRequires-Dist: gone\nRequires-Dist: old\n"),
               "gone": _Python315Leftover(None), "old": _Dist(None)}
    monkeypatch.setattr(sbom.metadata, "distribution", by_name.__getitem__)
    with warnings.catch_warnings():
        warnings.simplefilter("error")
        components = sbom.build_sbom("root")["components"]
    assert [c["name"] for c in components] == ["root"]
