"""``test/verify/macos_verify.py``: reported probes, and the judgement they share.

The script runs on a ``macos-14`` runner and nowhere else, so what can be held
here is its bookkeeping: a probe no runner has measured is *reported* and can
never fail the job, the pytest tally it builds two probes on counts a skip as
a skip, and the points arithmetic of the capture probe says what it should for
the layouts a runner cannot offer. No probe is run; nothing here touches a
screen, a window or an input device.
"""
import importlib.util
import re
from pathlib import Path
from types import ModuleType, SimpleNamespace

import pytest

REPO_ROOT = Path(__file__).resolve().parents[3]
SCRIPT = REPO_ROOT / "test" / "verify" / "macos_verify.py"
WORKFLOW = REPO_ROOT / ".github" / "workflows" / "platform-smoke.yml"


@pytest.fixture
def verify() -> ModuleType:
    spec = importlib.util.spec_from_file_location("macos_verify_under_test", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _probes(verify, monkeypatch, asserted, reported, expected):
    monkeypatch.setattr(verify, "PROBES", [
        (name, lambda value=value: verify.Outcome(value, "stub")) for name, value in asserted])
    monkeypatch.setattr(verify, "REPORTED", [
        (name, lambda value=value: verify.Outcome(value, "stub")) for name, value in reported])
    monkeypatch.setattr(verify, "EXPECTED", dict(expected))


def test_a_reported_probe_that_does_not_work_cannot_fail_the_job(verify, monkeypatch, capsys):
    _probes(verify, monkeypatch, [("a", True)], [("new", False)], {"a": True})
    assert verify.main([]) == 0
    output = capsys.readouterr().out
    assert "reported, not asserted" in output
    assert '"new": False,' in output, "the line EXPECTED would hold is printed"
    assert "1/1 probes match" in output


def test_a_reported_probe_that_raises_is_still_only_reported(verify, monkeypatch, capsys):
    _probes(verify, monkeypatch, [("a", True)], [], {"a": True})

    def boom():
        raise RuntimeError("no window server")

    monkeypatch.setattr(verify, "REPORTED", [("new", boom)])
    assert verify.main([]) == 0
    assert "\"new\": 'RuntimeError'," in capsys.readouterr().out


def test_an_asserted_probe_still_fails_the_job(verify, monkeypatch):
    _probes(verify, monkeypatch, [("a", False)], [("new", True)], {"a": True})
    assert verify.main([]) == 1


def test_a_probe_cannot_be_both_reported_and_expected(verify, monkeypatch, capsys):
    _probes(verify, monkeypatch, [("a", True)], [("new", True)], {"a": True, "new": True})
    assert verify.main([]) == 1
    assert "move it to PROBES" in capsys.readouterr().out


def test_measure_mode_lists_reported_probes_with_the_rest(verify, monkeypatch, capsys):
    _probes(verify, monkeypatch, [("a", True)], [("new", False)], {})
    assert verify.main(["--measure"]) == 0
    output = capsys.readouterr().out
    assert '"a": True,' in output and '"new": False,' in output


def test_no_shipped_probe_is_both_asserted_and_reported(verify):
    asserted = [name for name, _probe in verify.PROBES]
    reported = [name for name, _probe in verify.REPORTED]
    assert sorted(asserted) == sorted(verify.EXPECTED), "every asserted probe has an expectation"
    assert set(reported) & set(verify.EXPECTED) == set()
    assert len(set(asserted + reported)) == len(asserted + reported)


def test_the_reused_tests_exist_under_the_names_the_probes_run(verify):
    for node_ids, wanted in (verify.CLICK_STATE_TESTS, verify.MINIMISED_WINDOW_TESTS):
        assert wanted >= len(node_ids)
        for node_id in node_ids:
            path, _, function = node_id.partition("::")
            source = (REPO_ROOT / path).read_text(encoding="utf-8")
            assert re.search(rf"^def {re.escape(function)}\(", source, flags=re.MULTILINE), node_id


def test_the_tally_counts_a_skip_as_a_skip(verify):
    counts, reasons = verify.tally_test_report(
        "PASSED test/a.py::test_one[2]\n"
        "PASSED test/a.py::test_one[3]\n"
        "SKIPPED [2] test/b.py:140: no window appeared: no window server in this session\n"
        "FAILED test/c.py::test_two - AssertionError: restore did not bring it back\n"
        "ERROR test/d.py::test_three - RuntimeError\n"
        "=== 2 passed, 2 skipped, 1 failed, 1 error in 0.10s ===\n")
    assert counts == {"PASSED": 2, "FAILED": 1, "ERROR": 1, "SKIPPED": 2}
    assert reasons == ["test/b.py:140: no window appeared: no window server in this session"]


@pytest.mark.parametrize("report, wanted, worked", [
    ("PASSED a::t[2]\nPASSED a::t[3]\nPASSED a::u\n", 3, True),
    ("PASSED a::t[2]\nPASSED a::t[3]\n", 3, False),                       # one never ran
    ("PASSED a::t[2]\nPASSED a::t[3]\nSKIPPED [1] a.py:1: not darwin\n", 2, False),
    ("PASSED a::t\nFAILED a::u - boom\n", 1, False),
    ("", 1, False),                                                        # pytest missing
])
def test_reused_tests_work_only_when_every_one_really_passed(verify, monkeypatch, report, wanted, worked):
    class Done:
        returncode, stdout, stderr = 0, report, ""

    monkeypatch.setattr(verify, "subprocess", SimpleNamespace(run=lambda *_args, **_kwargs: Done()))
    outcome = verify.run_existing_tests(["a::t"], wanted)
    assert outcome.worked is worked, outcome.detail
    assert outcome.error is None


@pytest.mark.parametrize("frame, displays, region, expected", [
    # the runner: one 1x display, frame is its bounds at the origin
    (((1920, 1080), (0, 0)), [(0, 0, 1920, 1080)], ((64, 48), (10, 20)), True),
    # a Retina frame handed back in pixels is twice the bounds
    (((3840, 2160), (0, 0)), [(0, 0, 1920, 1080)], ((64, 48), (10, 20)), False),
    # a region in pixels
    (((1920, 1080), (0, 0)), [(0, 0, 1920, 1080)], ((128, 96), (10, 20)), False),
    # a second display to the left: the frame starts at its negative origin
    (((3360, 1080), (-1440, 0)), [(0, 0, 1920, 1080), (-1440, 0, 1440, 900)], ((64, 48), (10, 20)), True),
    (((1920, 1080), (0, 0)), [(0, 0, 1920, 1080), (-1440, 0, 1440, 900)], ((64, 48), (10, 20)), False),
    # Quartz reported nothing: the generic path ran, which is not this probe's answer
    (((1920, 1080), (0, 0)), [], ((64, 48), (10, 20)), False),
])
def test_the_capture_is_judged_in_points(verify, frame, displays, region, expected):
    assert verify.judge_logical_frame(frame, displays, region, (10, 20, 64, 48)) is expected


def test_the_smoke_job_installs_what_the_reused_tests_need():
    text = WORKFLOW.read_text(encoding="utf-8").replace("\r\n", "\n")
    job = text[text.index("  macos-capabilities:\n"):]
    assert re.search(r"pip install [^\n]*pytest==", job), (
        "two reported probes run tests through pytest; the job must install it")
    assert "run: python test/verify/macos_verify.py\n" in job, "the gate runs in assert mode"
