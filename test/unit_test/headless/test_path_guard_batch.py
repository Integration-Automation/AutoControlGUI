"""Headless tests for the CLI path guard. No Qt imports."""
import os
from pathlib import Path

import pytest

from je_auto_control.utils.path_guard import (
    ALLOWED_ROOTS_ENV, PathNotAllowedError, default_allowed_roots,
    validate_path,
)


# === canonicalisation ====================================================

def test_returns_a_resolved_absolute_path(tmp_path: Path):
    target = validate_path(tmp_path / "sub" / ".." / "bundle.json")
    assert target.is_absolute()
    assert ".." not in target.parts
    assert target.name == "bundle.json"


def test_relative_path_resolves_against_cwd(tmp_path: Path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    assert validate_path("out.pyi").parent == Path(os.path.realpath(tmp_path))


# === containment =========================================================

def test_traversal_outside_the_allowed_roots_is_rejected(tmp_path: Path):
    root = tmp_path / "workdir"
    root.mkdir()
    with pytest.raises(PathNotAllowedError):
        validate_path(root / ".." / "escaped.json", allowed_roots=[root])


def test_path_inside_an_explicit_root_is_accepted(tmp_path: Path):
    target = validate_path(tmp_path / "nested" / "bundle.json",
                           allowed_roots=[tmp_path])
    assert target.name == "bundle.json"


def test_env_var_extends_the_default_roots(tmp_path: Path, monkeypatch):
    outside = tmp_path / "volume"
    outside.mkdir()
    monkeypatch.setenv(ALLOWED_ROOTS_ENV, str(outside))
    assert str(outside) in [str(root) for root in default_allowed_roots()]
    assert validate_path(outside / "x.json").name == "x.json"


# === argument validation =================================================

def test_suffix_allowlist_is_enforced(tmp_path: Path):
    with pytest.raises(PathNotAllowedError):
        validate_path(tmp_path / "stub.txt", allowed_suffixes=(".pyi",))
    assert validate_path(tmp_path / "stub.PYI", allowed_suffixes=(".pyi",))


def test_missing_file_rejected_when_existence_required(tmp_path: Path):
    with pytest.raises(PathNotAllowedError):
        validate_path(tmp_path / "absent.json", must_exist=True)


def test_empty_and_nul_paths_are_rejected():
    with pytest.raises(PathNotAllowedError):
        validate_path("")
    with pytest.raises(PathNotAllowedError):
        validate_path("bundle\x00.json")


# === CLI wiring ==========================================================

def test_config_bundle_cli_refuses_a_path_outside_the_roots(capsys,
                                                            monkeypatch):
    from je_auto_control.utils.config_bundle import __main__ as cli
    monkeypatch.setenv(ALLOWED_ROOTS_ENV, "")
    blocked = Path(os.path.realpath(os.sep)) / "ac-escape-test.json"
    assert cli.main(["export", str(blocked)]) == 2
    assert "refusing to use that path" in capsys.readouterr().err
