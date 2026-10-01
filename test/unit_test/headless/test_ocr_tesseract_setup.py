"""Tesseract discovery, configuration and health checks (``ocr/tesseract_setup``).

A stand-in ``pytesseract`` replaces the real one, so no engine is run and no
screen is read. No Qt imports.
"""
import os
import subprocess  # nosec B404  # reason: only CalledProcessError is used, as a fake engine failure
import sys
import types

import pytest

import je_auto_control as ac
from je_auto_control.utils.exception.exceptions import AutoControlActionException
from je_auto_control.utils.ocr import tesseract_setup as setup
from je_auto_control.utils.ocr.backends import tesseract_backend
from je_auto_control.utils.ocr.backends.base import OCRBackendNotAvailableError
from je_auto_control.utils.ocr.backends.tesseract_backend import TesseractBackend


class _NotFound(OSError):
    """What pytesseract raises when the executable cannot be started."""


class _FakePytesseract:
    """The slice of ``pytesseract`` the setup helpers reach."""

    def __init__(self, languages=("eng",), cmd="tesseract"):
        self.pytesseract = types.SimpleNamespace(tesseract_cmd=cmd)
        self.languages = list(languages)
        self.version_error = None
        self.languages_error = None
        self.language_calls = []

    def get_tesseract_version(self):
        if self.version_error is not None:
            raise self.version_error
        return "5.3.0"

    def get_languages(self, config=""):
        self.language_calls.append(config)
        if self.languages_error is not None:
            raise self.languages_error
        return list(self.languages)


@pytest.fixture
def fake(monkeypatch, tmp_path):
    """A fake engine whose command is an existing file."""
    engine = tmp_path / "tesseract.exe"
    engine.write_bytes(b"")
    module = _FakePytesseract(languages=("jpn", "eng", "chi_tra"), cmd=str(engine))
    monkeypatch.setattr(tesseract_backend, "_pytesseract", module)
    return module


@pytest.fixture
def no_pytesseract(monkeypatch):
    monkeypatch.setattr(tesseract_backend, "_pytesseract", None)
    monkeypatch.setitem(sys.modules, "pytesseract", None)   # import -> ImportError


# --- ocr_languages: None and [] are different answers -----------------------

def test_languages_are_sorted_and_asked_with_an_empty_config(fake):
    assert setup.ocr_languages() == ["chi_tra", "eng", "jpn"]
    assert fake.language_calls == [""]


def test_an_engine_with_no_language_data_answers_an_empty_list(fake):
    fake.languages = []
    assert setup.ocr_languages() == []


def test_languages_are_none_when_the_package_is_missing(no_pytesseract):
    assert setup.ocr_languages() is None


def test_languages_are_none_when_the_engine_cannot_be_asked(fake):
    fake.languages_error = _NotFound("tesseract is not installed")
    assert setup.ocr_languages() is None


def test_languages_are_asked_afresh_on_every_call(fake):
    """Language data added while the process runs must be seen."""
    fake.languages = []
    assert setup.ocr_languages() == []
    fake.languages = ["eng"]
    assert setup.ocr_languages() == ["eng"]
    assert len(fake.language_calls) == 2


# --- ocr_status --------------------------------------------------------------

def test_status_ready(fake):
    status = setup.ocr_status()
    assert status == (True, setup.OCR_READY)
    ok, reason = status
    assert ok is True
    assert reason == "ready"
    assert status.ok is True
    assert status.reason == "ready"


def test_status_missing_package(no_pytesseract):
    assert setup.ocr_status() == (False, setup.OCR_MISSING_PACKAGE)


def test_status_missing_engine(fake, tmp_path):
    fake.pytesseract.tesseract_cmd = str(tmp_path / "absent" / "tesseract.exe")
    assert setup.ocr_status() == (False, setup.OCR_MISSING_ENGINE)


@pytest.mark.parametrize("error", [
    _NotFound("wrong architecture"),
    subprocess.CalledProcessError(1, ["tesseract", "--version"]),
    UnicodeDecodeError("utf-8", b"\xff", 0, 1, "invalid start byte"),
], ids=["os-error", "non-zero-exit", "undecodable-output"])
def test_status_engine_unusable(fake, error):
    fake.version_error = error
    assert setup.ocr_status() == (False, setup.OCR_ENGINE_UNUSABLE)


def test_an_unreadable_version_does_not_end_the_process(fake):
    """pytesseract raises SystemExit for a version string it cannot parse."""
    fake.version_error = SystemExit('Invalid tesseract version: "garbage"')
    assert setup.ocr_status() == (False, setup.OCR_ENGINE_UNUSABLE)
    backend = TesseractBackend()
    with pytest.raises(OCRBackendNotAvailableError):
        backend.version()


def test_status_no_language_data_only_when_the_engine_answered_empty(fake):
    fake.languages = []
    assert setup.ocr_status() == (False, setup.OCR_NO_LANGUAGE_DATA)
    # An engine that runs but cannot list is not "no language data".
    fake.languages_error = _NotFound("listing failed")
    assert setup.ocr_status() == (True, setup.OCR_READY)


def test_status_finds_a_bare_command_on_path(fake, monkeypatch):
    fake.pytesseract.tesseract_cmd = "tesseract"
    monkeypatch.setattr(setup, "shutil", types.SimpleNamespace(
        which=lambda name: r"C:\bin\tesseract.exe" if name == "tesseract" else None))
    assert setup.ocr_status() == (True, setup.OCR_READY)


# --- the engine command has one writer ---------------------------------------

def test_set_tesseract_cmd_is_what_status_checks(fake, tmp_path):
    other = tmp_path / "other-tesseract.exe"
    other.write_bytes(b"")
    ac.set_tesseract_cmd(str(other))
    assert fake.pytesseract.tesseract_cmd == str(other)
    assert TesseractBackend().cmd == str(other)
    assert setup.ocr_status().ok is True


# --- set_tessdata_dir ----------------------------------------------------------

def test_set_tessdata_dir_sets_the_resolved_directory(monkeypatch, tmp_path):
    monkeypatch.delenv(setup.TESSDATA_ENV, raising=False)
    data = tmp_path / "tessdata"
    data.mkdir()
    resolved = setup.set_tessdata_dir(data)
    assert resolved == os.path.realpath(data)
    assert os.environ[setup.TESSDATA_ENV] == resolved


def test_set_tessdata_dir_none_restores_the_engine_default(monkeypatch, tmp_path):
    monkeypatch.setenv(setup.TESSDATA_ENV, str(tmp_path))
    assert setup.set_tessdata_dir(None) is None
    assert setup.TESSDATA_ENV not in os.environ


def test_set_tessdata_dir_refuses_what_is_not_a_directory(monkeypatch, tmp_path):
    monkeypatch.setenv(setup.TESSDATA_ENV, "kept")
    a_file = tmp_path / "eng.traineddata"
    a_file.write_bytes(b"")
    for bad in (tmp_path / "absent", a_file):
        with pytest.raises(AutoControlActionException):
            setup.set_tessdata_dir(bad)
    assert os.environ[setup.TESSDATA_ENV] == "kept"


# --- find_tesseract_cmd ----------------------------------------------------------

def _no_path(monkeypatch):
    monkeypatch.setattr(setup, "shutil", types.SimpleNamespace(which=lambda name: None))


def test_find_prefers_the_environment_override(monkeypatch, tmp_path):
    engine = tmp_path / "custom-tesseract.exe"
    engine.write_bytes(b"")
    monkeypatch.setenv(setup.TESSERACT_CMD_ENV, f"  {engine}  ")
    monkeypatch.setattr(setup, "shutil", types.SimpleNamespace(
        which=lambda name: pytest.fail("PATH must not be searched")))
    assert setup.find_tesseract_cmd() == os.path.abspath(engine)


def test_find_ignores_an_override_naming_no_file(monkeypatch, tmp_path):
    monkeypatch.setenv(setup.TESSERACT_CMD_ENV, str(tmp_path / "absent.exe"))
    found = tmp_path / "on-path" / "tesseract.exe"
    monkeypatch.setattr(setup, "shutil", types.SimpleNamespace(which=lambda name: str(found)))
    assert setup.find_tesseract_cmd() == os.path.abspath(found)


def test_find_falls_back_to_the_install_locations(monkeypatch, tmp_path):
    monkeypatch.delenv(setup.TESSERACT_CMD_ENV, raising=False)
    _no_path(monkeypatch)
    installed = tmp_path / "Tesseract-OCR" / "tesseract.exe"
    installed.parent.mkdir()
    installed.write_bytes(b"")
    monkeypatch.setattr(setup, "_install_candidates",
                        lambda: [str(tmp_path / "missing.exe"), str(installed)])
    assert setup.find_tesseract_cmd() == str(installed)


def test_find_returns_none_when_nothing_is_installed(monkeypatch, tmp_path):
    monkeypatch.delenv(setup.TESSERACT_CMD_ENV, raising=False)
    _no_path(monkeypatch)
    monkeypatch.setattr(setup, "_install_candidates", lambda: [str(tmp_path / "missing.exe")])
    assert setup.find_tesseract_cmd() is None


def test_install_locations_per_platform(monkeypatch):
    monkeypatch.setenv("ProgramFiles", r"D:\Apps")
    monkeypatch.delenv("ProgramFiles(x86)", raising=False)
    monkeypatch.setenv("LOCALAPPDATA", r"D:\Users\me\AppData\Local")
    windows = setup._install_candidates("win32")
    assert os.path.join(r"D:\Apps", "Tesseract-OCR", "tesseract.exe") in windows
    assert os.path.join(r"C:\Program Files (x86)", "Tesseract-OCR", "tesseract.exe") in windows
    assert os.path.join(r"D:\Users\me\AppData\Local", "Programs", "Tesseract-OCR",
                        "tesseract.exe") in windows
    assert "/opt/homebrew/bin/tesseract" in setup._install_candidates("darwin")
    assert "/usr/bin/tesseract" in setup._install_candidates("linux")
    assert "/usr/bin/tesseract" in setup._install_candidates("freebsd14")


# --- wiring ------------------------------------------------------------------------

def test_executor_commands_return_json_friendly_dicts(fake):
    from je_auto_control.utils.executor.action_executor import executor
    assert executor.event_dict["AC_ocr_status"]() == {"ok": True, "reason": "ready"}
    assert executor.event_dict["AC_ocr_languages"]() == {"languages": ["chi_tra", "eng", "jpn"]}
    fake.languages_error = _NotFound("listing failed")
    assert executor.event_dict["AC_ocr_languages"]() == {"languages": None}


def test_mcp_tools_and_script_builder_specs():
    from je_auto_control.utils.mcp_server.tools import build_default_tool_registry
    tools = {tool.name: tool for tool in build_default_tool_registry()}
    assert {"ac_ocr_status", "ac_ocr_languages"} <= set(tools)
    assert tools["ac_ocr_status"].annotations.read_only is True
    from je_auto_control.gui.script_builder.command_schema import _build_specs
    assert {"AC_ocr_status", "AC_ocr_languages"} <= {s.command for s in _build_specs()}


def test_mcp_handlers_return_json_friendly_dicts(fake):
    from je_auto_control.utils.mcp_server.tools import _handlers_screen
    assert _handlers_screen.ocr_status() == {"ok": True, "reason": "ready"}
    fake.languages = []
    assert _handlers_screen.ocr_languages() == {"languages": []}


def test_facade_exports():
    for name in ("OCRStatus", "find_tesseract_cmd", "ocr_languages", "ocr_status",
                 "set_tessdata_dir"):
        assert hasattr(ac, name), name
        assert name in ac.__all__, name
