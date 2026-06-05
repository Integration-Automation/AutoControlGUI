"""Headless tests for clipboard assertion + assertion combinators (no Qt)."""
import time

import pytest

import je_auto_control as ac
from je_auto_control.utils.assertion import (
    AssertionResult, GroupAssertionResult, assert_all, assert_any,
    assert_clipboard, assert_eventually, assert_file, assert_http,
    assert_process, run_assertion_spec,
)
from je_auto_control.utils.exception.exceptions import (
    AutoControlAssertionException,
)


def _patch_clipboard(monkeypatch, value):
    import je_auto_control.utils.clipboard.clipboard as clip
    monkeypatch.setattr(clip, "get_clipboard", lambda: value)


def _patch_windows(monkeypatch, titles):
    import je_auto_control.wrapper.auto_control_window as win
    monkeypatch.setattr(
        win, "list_windows",
        lambda: [(i, t) for i, t in enumerate(titles)],
    )


# === facade exports ========================================================

def test_facade_exports_new_assertions():
    for name in ("assert_clipboard", "assert_process", "assert_file",
                 "assert_http", "assert_all", "assert_eventually",
                 "run_assertion_spec", "GroupAssertionResult"):
        assert hasattr(ac, name), name


# === assert_clipboard ======================================================

def test_assert_clipboard_equals_passes(monkeypatch):
    _patch_clipboard(monkeypatch, "hello world")
    result = assert_clipboard("hello world")
    assert isinstance(result, AssertionResult)
    assert result.passed is True
    assert result.kind == "clipboard"


def test_assert_clipboard_contains(monkeypatch):
    _patch_clipboard(monkeypatch, "order 12345 confirmed")
    assert assert_clipboard("12345", mode="contains").passed is True


def test_assert_clipboard_regex(monkeypatch):
    _patch_clipboard(monkeypatch, "token=ab12cd")
    assert assert_clipboard(r"token=\w+", mode="regex").passed is True


def test_assert_clipboard_ignore_case(monkeypatch):
    _patch_clipboard(monkeypatch, "DONE")
    assert assert_clipboard("done", ignore_case=True).passed is True


def test_assert_clipboard_mismatch_raises(monkeypatch):
    _patch_clipboard(monkeypatch, "something else")
    with pytest.raises(AutoControlAssertionException):
        assert_clipboard("expected", mode="equals")


def test_assert_clipboard_present_false(monkeypatch):
    """A cleared clipboard should pass present=False (secret removed)."""
    _patch_clipboard(monkeypatch, "")
    assert assert_clipboard("secret", mode="contains", present=False).passed


def test_assert_clipboard_unknown_mode_raises(monkeypatch):
    _patch_clipboard(monkeypatch, "x")
    with pytest.raises(AutoControlAssertionException):
        assert_clipboard("x", mode="bogus")


# === assert_process ========================================================

def _patch_process_names(monkeypatch, names):
    import je_auto_control.utils.assertion.assertions as a
    monkeypatch.setattr(a, "_running_process_names", lambda needle: list(names))


def test_assert_process_running_passes(monkeypatch):
    _patch_process_names(monkeypatch, ["notepad.exe"])
    result = assert_process("notepad")
    assert result.passed is True
    assert result.kind == "process"


def test_assert_process_absent_raises(monkeypatch):
    _patch_process_names(monkeypatch, [])
    with pytest.raises(AutoControlAssertionException):
        assert_process("notepad")


def test_assert_process_expect_not_running(monkeypatch):
    _patch_process_names(monkeypatch, [])
    assert assert_process("notepad", running=False).passed is True


# === assert_file ===========================================================

def test_assert_file_exists_and_contains(tmp_path):
    f = tmp_path / "report.txt"
    f.write_text("status: OK\ntotal: 42\n", encoding="utf-8")
    result = assert_file(str(f), contains="total: 42")
    assert result.passed is True
    assert result.kind == "file"


def test_assert_file_missing_raises(tmp_path):
    with pytest.raises(AutoControlAssertionException):
        assert_file(str(tmp_path / "nope.txt"))


def test_assert_file_expect_absent(tmp_path):
    assert assert_file(str(tmp_path / "nope.txt"), exists=False).passed is True


def test_assert_file_min_size_fail(tmp_path):
    f = tmp_path / "small.bin"
    f.write_bytes(b"ab")
    result = assert_file(str(f), min_size=100, raise_on_fail=False)
    assert result.passed is False
    assert "min_size" in result.message


def test_assert_file_sha256(tmp_path):
    import hashlib
    f = tmp_path / "data.bin"
    data = b"hello"
    f.write_bytes(data)
    digest = hashlib.sha256(data).hexdigest()
    assert assert_file(str(f), sha256=digest).passed is True
    bad = assert_file(str(f), sha256="0" * 64, raise_on_fail=False)
    assert bad.passed is False


def test_assert_file_contains_missing(tmp_path):
    f = tmp_path / "log.txt"
    f.write_text("nothing here", encoding="utf-8")
    result = assert_file(str(f), contains="ERROR", raise_on_fail=False)
    assert result.passed is False


# === assert_http ===========================================================

class _FakeResp:
    def __init__(self, status, body):
        self.status = status
        self._body = body

    def read(self):
        return self._body

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


def _patch_urlopen(monkeypatch, resp_or_exc):
    import urllib.request

    def _fake(request, timeout=None):
        if isinstance(resp_or_exc, Exception):
            raise resp_or_exc
        return resp_or_exc

    monkeypatch.setattr(urllib.request, "urlopen", _fake)


def test_assert_http_status_ok(monkeypatch):
    _patch_urlopen(monkeypatch, _FakeResp(200, b"pong"))
    result = assert_http("https://example.test/health")
    assert result.passed is True
    assert result.kind == "http"


def test_assert_http_body_contains(monkeypatch):
    _patch_urlopen(monkeypatch, _FakeResp(200, b'{"ready": true}'))
    assert assert_http("https://x.test", contains='"ready": true').passed


def test_assert_http_wrong_status_raises(monkeypatch):
    _patch_urlopen(monkeypatch, _FakeResp(500, b"err"))
    with pytest.raises(AutoControlAssertionException):
        assert_http("https://x.test", status=200)


def test_assert_http_unreachable_is_failure(monkeypatch):
    import urllib.error
    _patch_urlopen(monkeypatch, urllib.error.URLError("refused"))
    result = assert_http("https://x.test", raise_on_fail=False)
    assert result.passed is False
    assert "unreachable" in result.message


def test_assert_http_rejects_non_http_scheme():
    with pytest.raises(AutoControlAssertionException):
        assert_http("file:///etc/passwd")


# === run_assertion_spec ====================================================

def test_run_assertion_spec_dispatches(monkeypatch):
    _patch_windows(monkeypatch, ["Notepad"])
    result = run_assertion_spec({"kind": "window", "title": "Notepad"})
    assert result.passed is True


def test_run_assertion_spec_unknown_kind():
    with pytest.raises(AutoControlAssertionException):
        run_assertion_spec({"kind": "nope"})


def test_run_assertion_spec_requires_mapping():
    with pytest.raises(AutoControlAssertionException):
        run_assertion_spec(["not", "a", "mapping"])


def test_run_assertion_spec_never_raises_on_fail(monkeypatch):
    """raise_on_fail inside the spec is overridden to False by default."""
    _patch_windows(monkeypatch, ["Calculator"])
    result = run_assertion_spec(
        {"kind": "window", "title": "Notepad", "raise_on_fail": True}
    )
    assert result.passed is False


# === assert_all (soft assertions) ==========================================

def test_assert_all_collects_every_failure(monkeypatch):
    _patch_windows(monkeypatch, ["Calculator"])
    _patch_clipboard(monkeypatch, "wrong")
    specs = [
        {"kind": "window", "title": "Notepad"},      # fails
        {"kind": "window", "title": "Calculator"},   # passes
        {"kind": "clipboard", "text": "right"},      # fails
    ]
    group = assert_all(specs, raise_on_fail=False)
    assert isinstance(group, GroupAssertionResult)
    assert group.total == 3
    assert group.failed == 2
    assert group.passed is False
    assert len(group.failures()) == 2
    assert "2/3 assertions failed" in group.message


def test_assert_all_all_pass(monkeypatch):
    _patch_windows(monkeypatch, ["Notepad", "Calculator"])
    group = assert_all([
        {"kind": "window", "title": "Notepad"},
        {"kind": "window", "title": "Calculator"},
    ])
    assert group.passed is True
    assert group.failed == 0


def test_assert_all_raises_with_aggregate(monkeypatch):
    _patch_windows(monkeypatch, ["Calculator"])
    with pytest.raises(AutoControlAssertionException) as exc:
        assert_all([
            {"kind": "window", "title": "Notepad"},
            {"kind": "window", "title": "Firefox"},
        ])
    assert "2/2 assertions failed" in str(exc.value)


def test_assert_all_to_dict(monkeypatch):
    _patch_windows(monkeypatch, ["Notepad"])
    group = assert_all([{"kind": "window", "title": "Notepad"}])
    data = group.to_dict()
    assert data["passed"] is True
    assert data["total"] == 1
    assert "message" in data


# === assert_any (OR-combinator) ============================================

def test_assert_any_passes_if_one_passes(monkeypatch):
    _patch_windows(monkeypatch, ["Calculator"])
    group = assert_any([
        {"kind": "window", "title": "Notepad"},      # fails
        {"kind": "window", "title": "Calculator"},   # passes
    ])
    assert isinstance(group, GroupAssertionResult)
    assert group.passed is True


def test_assert_any_short_circuits(monkeypatch):
    _patch_windows(monkeypatch, ["Calculator"])
    group = assert_any([
        {"kind": "window", "title": "Calculator"},   # passes first
        {"kind": "window", "title": "Notepad"},      # never evaluated
    ])
    assert group.total == 1


def test_assert_any_all_fail_raises(monkeypatch):
    _patch_windows(monkeypatch, ["Calculator"])
    with pytest.raises(AutoControlAssertionException):
        assert_any([
            {"kind": "window", "title": "Notepad"},
            {"kind": "window", "title": "Firefox"},
        ])


def test_assert_any_all_fail_no_raise(monkeypatch):
    _patch_windows(monkeypatch, ["Calculator"])
    group = assert_any([
        {"kind": "window", "title": "Notepad"},
    ], raise_on_fail=False)
    assert group.passed is False


# === assert_eventually =====================================================

def test_assert_eventually_passes_on_later_attempt(monkeypatch):
    titles = {"value": ["Loading"]}
    import je_auto_control.wrapper.auto_control_window as win
    monkeypatch.setattr(
        win, "list_windows",
        lambda: [(0, t) for t in titles["value"]],
    )

    calls = {"n": 0}
    real_spec = run_assertion_spec

    def _flip(spec, raise_on_fail=False):
        calls["n"] += 1
        if calls["n"] >= 3:
            titles["value"] = ["Done"]
        return real_spec(spec, raise_on_fail=raise_on_fail)

    import je_auto_control.utils.assertion.combinators as comb
    monkeypatch.setattr(comb, "run_assertion_spec", _flip)
    result = assert_eventually(
        {"kind": "window", "title": "Done"},
        timeout=2.0, interval=0.01,
    )
    assert result.passed is True
    assert calls["n"] >= 3


def test_assert_eventually_times_out_raises(monkeypatch):
    _patch_windows(monkeypatch, ["Loading"])
    with pytest.raises(AutoControlAssertionException) as exc:
        assert_eventually(
            {"kind": "window", "title": "Done"},
            timeout=0.05, interval=0.01,
        )
    assert "assert_eventually failed" in str(exc.value)


def test_assert_eventually_timeout_no_raise(monkeypatch):
    _patch_windows(monkeypatch, ["Loading"])
    result = assert_eventually(
        {"kind": "window", "title": "Done"},
        timeout=0.05, interval=0.01, raise_on_fail=False,
    )
    assert result.passed is False
    assert "assert_eventually failed" in result.message


def test_assert_eventually_negative_timeout_rejected():
    with pytest.raises(AutoControlAssertionException):
        assert_eventually({"kind": "window", "title": "x"}, timeout=-1)


def test_assert_eventually_returns_fast_when_already_true(monkeypatch):
    _patch_windows(monkeypatch, ["Done"])
    started = time.monotonic()
    result = assert_eventually(
        {"kind": "window", "title": "Done"}, timeout=5.0, interval=1.0,
    )
    assert result.passed is True
    assert time.monotonic() - started < 1.0


# === executor wiring =======================================================

def test_executor_commands_registered():
    from je_auto_control.utils.executor.action_executor import executor
    for cmd in ("AC_assert_clipboard", "AC_assert_process", "AC_assert_file",
                "AC_assert_http", "AC_assert_all", "AC_assert_any",
                "AC_assert_eventually"):
        assert cmd in executor.event_dict, cmd
