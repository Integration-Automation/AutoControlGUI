"""Under TestPioneer a report asked for under a relative name goes below ``TEST_PIONEER_ARTIFACT_DIR``."""
from pathlib import Path

import pytest

from je_auto_control.utils.generate_report.generate_html_report import generate_html_report
from je_auto_control.utils.generate_report.generate_json_report import generate_json_report
from je_auto_control.utils.generate_report.generate_xml_report import generate_xml_report
from je_auto_control.utils.generate_report.report_path import ARTIFACT_DIR_VARIABLE, report_path
from je_auto_control.utils.test_record.record_test_class import test_record_instance


@pytest.fixture(autouse=True)
def _records():
    saved = list(test_record_instance.test_record_list)
    test_record_instance.test_record_list[:] = [
        {"function_name": "ok_func", "local_param": None, "time": "t", "program_exception": "None"},
        {"function_name": "bad_func", "local_param": None, "time": "t", "program_exception": "boom"},
    ]
    yield
    test_record_instance.test_record_list[:] = saved


@pytest.fixture
def artifact_dir(tmp_path, monkeypatch):
    """A TestPioneer run: the variable is set, and the working directory is somewhere else."""
    directory = tmp_path / "artifacts" / "run-1" / "runners" / "gui-runner" / "01-gui"
    work = tmp_path / "work"
    work.mkdir()
    monkeypatch.chdir(work)
    monkeypatch.setenv(ARTIFACT_DIR_VARIABLE, str(directory))
    return directory


def test_a_name_is_returned_as_given_outside_testpioneer(monkeypatch):
    monkeypatch.delenv(ARTIFACT_DIR_VARIABLE, raising=False)
    assert report_path("reports/gui") == "reports/gui"


def test_an_empty_variable_counts_as_unset(monkeypatch):
    monkeypatch.setenv(ARTIFACT_DIR_VARIABLE, "  ")
    assert report_path("reports/gui") == "reports/gui"


def test_a_relative_name_goes_below_the_artifact_directory(artifact_dir):
    target = Path(report_path("reports/gui_success.json"))
    assert target == artifact_dir.resolve() / "reports" / "gui_success.json"
    assert target.parent.is_dir()


def test_an_absolute_name_is_left_alone(artifact_dir, tmp_path):
    name = str(tmp_path / "elsewhere" / "gui.json")
    assert report_path(name) == name
    assert not artifact_dir.exists()


def test_a_name_that_leaves_the_directory_is_left_alone(artifact_dir):
    assert report_path("../outside.json") == "../outside.json"
    assert not artifact_dir.exists()


def test_a_directory_that_cannot_be_created_falls_back_to_the_name(tmp_path, monkeypatch):
    not_a_directory = tmp_path / "file"
    not_a_directory.write_text("x", encoding="utf-8")
    monkeypatch.setenv(ARTIFACT_DIR_VARIABLE, str(not_a_directory))
    assert report_path("reports/gui.json") == "reports/gui.json"


@pytest.mark.parametrize("generate, written", [
    (generate_json_report, ["reports/gui_success.json", "reports/gui_failure.json"]),
    (generate_xml_report, ["reports/gui_success.xml", "reports/gui_failure.xml"]),
    (generate_html_report, ["reports/gui.html"]),
], ids=["json", "xml", "html"])
def test_a_report_is_written_below_the_artifact_directory(artifact_dir, generate, written):
    generate("reports/gui")
    assert [(artifact_dir / path).is_file() for path in written] == [True] * len(written)
    # Nothing is left in the working directory, where the name used to point.
    assert not Path("reports").exists()


def test_outside_testpioneer_a_report_stays_in_the_working_directory(tmp_path, monkeypatch):
    monkeypatch.delenv(ARTIFACT_DIR_VARIABLE, raising=False)
    monkeypatch.chdir(tmp_path)
    generate_json_report("gui")
    assert (tmp_path / "gui_success.json").is_file()
